# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Gmail Adapter.

Bridges MailDesk application logic to Odoo/external interfaces for Gmail Adapter.
Layer: interface adapters.
"""

import logging
from datetime import datetime, timezone
from typing import Any, List

from ..domain.contracts import Message
from ..domain.services.normalization import msgid_header, parse_msgid_list

_logger = logging.getLogger(__name__)


class GmailAdapter:
    """
    Adapter to normalize Gmail API responses into canonical domain contracts.
    """

    def __init__(self, sync_env):
        self.sync = sync_env

    def fetch_metadata_batch(
        self,
        service: Any,
        account_id: int,
        folder_name: str,
        ids: List[str],
    ) -> List[Message]:
        """
        Fetch headers/metadata for proper Gmail message IDs and return canonical Messages.
        """
        if not ids:
            return []

        results = {}

        def _cb(request_id, response, exception):
            if exception is None and response:
                results[request_id] = response

        # Batch fetch from Gmail
        for i in range(0, len(ids), 50):
            batch = service.new_batch_http_request(callback=_cb)
            for mid in ids[i : i + 50]:
                batch.add(
                    service.users().messages().get(userId="me", id=mid, format="full"),
                    request_id=mid,
                )
            try:
                batch.execute()
            except Exception as e:
                _logger.debug("Gmail fetch_metadata_batch error: %s", e)

        messages = []
        for mid in ids:
            m = results.get(mid)
            if not m:
                continue

            payload = m.get("payload") or {}
            headers = payload.get("headers") or []
            hdr = {
                (h.get("name") or "").lower(): (h.get("value") or "") for h in headers
            }
            lbls = set(m.get("labelIds") or [])

            # Date parsing
            ts = 0
            try:
                ts = int(m.get("internalDate") or 0)
            except Exception:
                ts = 0
            dt = (
                datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).replace(
                    tzinfo=None
                )
                if ts
                else datetime(1970, 1, 1)
            )

            # Header parsing
            subject = (
                self.sync._decode_header_value(hdr.get("subject") or "")
                or "(no subject)"
            )

            # From parsing
            parsed_from = self.sync._parse_sender_header(hdr.get("from") or "")
            # (formatted, name, email)
            sender_name = parsed_from[1]
            sender_email = parsed_from[2]

            to_display = self.sync._decode_header_value(hdr.get("to") or "")
            cc_display = self.sync._decode_header_value(hdr.get("cc") or "")
            bcc_display = self.sync._decode_header_value(hdr.get("bcc") or "")

            # Snippet
            snippet = (m.get("snippet") or "")[:120]

            # Flags
            is_unread = "UNREAD" in lbls
            is_starred = "STARRED" in lbls

            # Attachments logic (extracted helper)
            has_atts = self._has_atts(payload)

            # Canonical IDs
            msg_id_norm = msgid_header(hdr.get("message-id") or "")

            # In-Reply-To / References?
            # Gmail headers usually include them.
            in_reply_to = msgid_header(hdr.get("in-reply-to") or "")
            references = " ".join(parse_msgid_list(hdr.get("references") or ""))

            outgoing_id = (hdr.get("x-maildesk-outgoing-id") or "").strip()

            # Thread ID
            thread_id = m.get("threadId")  # Gmail thread ID is reliable

            # Use Gmail ID itself as Thread contract ID?
            # Or map?
            # Domain contract `Thread` has `id`.
            # Message contract `thread_id` should match.

            # Create Message
            msg = Message(
                id=m.get("id"),  # Gmail ID (string)
                thread_id=thread_id,
                account_id=account_id,
                message_header_id=msg_id_norm,
                in_reply_to=in_reply_to,
                references=references,
                date=dt,
                subject=subject,
                email_from=(sender_email or "").lower(),
                sender_display_name=sender_name,
                to_display=to_display,
                cc_display=cc_display,
                bcc_display=bcc_display,
                snippet=snippet,
                outgoing_id=outgoing_id,
                folder_ids=[folder_name],
                is_read=not is_unread,
                is_starred=is_starred,
                has_attachments=has_atts,
                metadata={"label_ids": list(lbls)},
            )
            messages.append(msg)

        return messages

    def _has_atts(self, payload):
        """Helper to detect attachments in Gmail payload structure"""
        if not payload:
            return False
        stack = [payload]
        while stack:
            p = stack.pop()
            b = p.get("body") or {}
            # If filename present or explicit attachmentId in body
            if (p.get("filename") or "").strip() or b.get("attachmentId"):
                return True
            parts = p.get("parts") or []
            for x in parts:
                if x:
                    stack.append(x)
        return False
