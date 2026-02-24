# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Outlook Adapter.

Bridges MailDesk application logic to Odoo/external interfaces for Outlook Adapter.
Layer: interface adapters.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, List, Optional

from ..domain.contracts import Message
from ..domain.services.normalization import msgid_header, parse_msgid_list

_logger = logging.getLogger(__name__)


class OutlookAdapter:
    """
    Adapter to normalize Microsoft Graph API responses into canonical domain contracts.
    """

    def __init__(self, sync_env):
        self.sync = sync_env

    def fetch_metadata_batch(
        self,
        sess: Any,
        base_url: str,
        account_id: int,
        folder_name: str,
        ids: List[str],
    ) -> List[Message]:
        """
        Fetch headers/metadata for Outlook message IDs and return canonical Messages.
        """
        if not ids:
            return []

        base_headers = {"Prefer": 'outlook.body-content-type="text"'}
        sess.headers.update(base_headers)

        def fetch_one(mid):
            sel = (
                "id,subject,from,receivedDateTime,hasAttachments,importance,isRead,"
                "ccRecipients,toRecipients,conversationId,flag,internetMessageId,bodyPreview,internetMessageHeaders"
            )
            url = f"{base_url}/me/messages/{mid}?$select={sel}"

            for attempt in range(5):
                r = sess.get(url, timeout=30)
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    delay = int(ra) if (ra and ra.isdigit()) else (1 + attempt)
                    time.sleep(delay)
                    continue
                r.raise_for_status()
                return r.json()
            raise Exception("Outlook Graph throttling: too many 429s")

        max_workers = min(4, len(ids))
        raw_messages = []

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(fetch_one, i) for i in ids]
            for fut in as_completed(futures):
                try:
                    raw_messages.append(fut.result())
                except Exception as e:
                    _logger.debug("Outlook fetch error: %s", e)

        messages = []
        for m in raw_messages:
            # Parse headers
            headers = m.get("internetMessageHeaders") or []
            in_reply_to = ""
            references = ""
            outgoing_id = ""
            for h in headers:
                name = (h.get("name") or "").lower()
                value = h.get("value") or ""
                if name == "in-reply-to":
                    in_reply_to = value
                elif name == "references":
                    references = value
                elif name == "x-maildesk-outgoing-id":
                    outgoing_id = value

            # Parse sender
            sender = ((m.get("from") or {}).get("emailAddress") or {}).get(
                "address", ""
            ) or ""
            sender_name = ((m.get("from") or {}).get("emailAddress") or {}).get(
                "name", ""
            ) or ""
            email_from = sender.lower()

            # Parse date
            dt_raw = (
                m.get("receivedDateTime")
                or m.get("sentDateTime")
                or m.get("createdDateTime")
            )
            msg_dt = self._parse_graph_datetime(dt_raw)

            # Parse recipients
            to_disp = ", ".join(
                [
                    (x.get("emailAddress") or {}).get("address", "")
                    for x in (m.get("toRecipients") or [])
                ]
            )
            cc_disp = ", ".join(
                [
                    (x.get("emailAddress") or {}).get("address", "")
                    for x in (m.get("ccRecipients") or [])
                ]
            )

            # Parse preview
            preview = (m.get("bodyPreview") or "").strip()
            if preview:
                preview = preview.replace("\r", " ").replace("\n", " ")
                if len(preview) > 160:
                    preview = preview[:160]

            # Parse flags
            flag = (m.get("flag") or {}).get("flagStatus")
            is_starred = flag == "flagged"
            is_read = bool(m.get("isRead"))

            # Parse attachments
            has_atts = bool(m.get("hasAttachments"))

            # Canonical IDs
            msg_id_norm = msgid_header(m.get("internetMessageId") or "")
            thread_id = m.get("conversationId") or ""

            # Create Message contract
            msg = Message(
                id=m.get("id"),  # Outlook Graph ID (string)
                thread_id=thread_id,
                account_id=account_id,
                message_header_id=msg_id_norm,
                in_reply_to=msgid_header(in_reply_to),
                references=" ".join(parse_msgid_list(references)),
                date=msg_dt,
                subject=m.get("subject") or "(no subject)",
                email_from=email_from,
                sender_display_name=sender_name,
                to_display=to_disp,
                cc_display=cc_disp,
                bcc_display="",  # Graph doesn't expose BCC in list view
                snippet=preview,
                outgoing_id=(outgoing_id or "").strip(),
                folder_ids=[folder_name],
                is_read=is_read,
                is_starred=is_starred,
                has_attachments=has_atts,
                metadata={},  # Outlook uses id directly, no provider-specific metadata needed
            )
            messages.append(msg)

        return messages

    def _parse_graph_datetime(self, dt_raw: Optional[str]) -> datetime:
        """Parse Microsoft Graph datetime string to Python datetime"""
        if not dt_raw:
            return datetime(1970, 1, 1)

        try:
            # Graph returns ISO 8601 with Z suffix
            if dt_raw.endswith("Z"):
                dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(dt_raw)

            # Strip timezone info for Odoo compatibility
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return datetime(1970, 1, 1)
