# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk IMAP Adapter.

Bridges MailDesk application logic to Odoo/external interfaces for IMAP Adapter.
Layer: interface adapters.
"""

import logging

from typing import Any, List

from email import policy
from email.parser import BytesParser

from ..domain.contracts import Message
from ..domain.services.normalization import msgid_header, norm_msgid, parse_msgid_list
from ..infrastructure.rendering.preview_extractor import MAX_PREVIEW_BYTES
from ..infrastructure.utils.imap_fetch import pick_imap_body_bytes

_logger = logging.getLogger(__name__)


class ImapAdapter:
    """
    Adapter to normalize IMAP provider responses into canonical domain contracts.
    """

    def __init__(self, sync_env):
        self.sync = sync_env

    def fetch_metadata_batch(
        self, uids: List[int], folder_name: str, account_id: int, pool: Any
    ) -> List[Message]:
        """
        Fetch metadata for the given UIDs and return canonical Message objects.
        This adapts the raw IMAP fetch response into the domain contract.
        """
        if not uids:
            return []

        data = {}
        try:
            with pool.session() as client:
                client.select_folder(folder_name, readonly=True)
                # Fetch command matching legacy _full_fetch fields
                data = (
                    client.fetch(
                        uids,
                        [
                            "ENVELOPE",
                            "FLAGS",
                            "UID",
                            "BODYSTRUCTURE",
                            "BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC MESSAGE-ID IN-REPLY-TO REFERENCES X-MAILDESK-OUTGOING-ID)]",
                            f"BODY.PEEK[]<0.{MAX_PREVIEW_BYTES}>",
                        ],
                    )
                    or {}
                )
        except Exception as e:
            # Swallow error as per legacy behavior (returns empty dict/list)
            _logger.debug("IMAP fetch_metadata_batch failed: %s", e)
            return []

        messages = []
        for uid in uids:
            d = data.get(uid, {}) or {}
            env = d.get(b"ENVELOPE")
            flags = d.get(b"FLAGS") or []

            # Parse Headers
            hdr_bytes = (
                d.get(
                    b"BODY[HEADER.FIELDS (SUBJECT FROM TO CC MESSAGE-ID IN-REPLY-TO REFERENCES X-MAILDESK-OUTGOING-ID)]",
                    b"",
                )
                or d.get(
                    b"BODY[HEADER.FIELDS (SUBJECT FROM TO CC MESSAGE-ID IN-REPLY-TO REFERENCES)]",
                    b"",
                )
                or b""
            )
            hdr_msg = BytesParser(policy=policy.default).parsebytes(hdr_bytes or b"")

            subject_raw = str(hdr_msg.get("Subject") or "")
            from_raw = str(hdr_msg.get("From") or "")
            raw_msgid = str(hdr_msg.get("Message-ID") or "")
            raw_irt = str(hdr_msg.get("In-Reply-To") or "")
            raw_refs = str(hdr_msg.get("References") or "")
            outgoing_id = str(hdr_msg.get("X-MailDesk-Outgoing-ID") or "").strip()

            sender_email = ""
            sender_name = ""
            if from_raw:
                parsed = self.sync._parse_sender_header(from_raw.strip())
                sender_name = parsed[1]
                sender_email = parsed[2]

            # Normalization helpers from sync service
            subject = self.sync._decode_header_value(subject_raw) or "(no subject)"
            msg_date = self.sync._to_datetime(env.date if env else None)
            to_disp = self.sync._join_addresses(env.to if env else None)
            cc_disp = self.sync._join_addresses(env.cc if env else None)

            # Threading
            message_id_hdr = msgid_header(raw_msgid)
            in_reply_hdr = msgid_header(raw_irt)
            references_hdr = " ".join(parse_msgid_list(raw_refs))

            first_ref = ""
            if references_hdr:
                refs = parse_msgid_list(references_hdr)
                if refs:
                    first_ref = norm_msgid(refs[0])

            thread_id = (
                first_ref or norm_msgid(in_reply_hdr) or norm_msgid(message_id_hdr)
            )

            body_bytes = pick_imap_body_bytes(d)

            preview = (
                self.sync._extract_imap_preview(body_bytes, subject)
                if body_bytes
                else ""
            )

            # Flags
            # Match strict flags from L1957 logic
            is_read = any(
                f in flags for f in [b"\\Seen", b"\\seen", "\\Seen", "\\seen"]
            )
            is_starred = b"\\Flagged" in flags or "\\Flagged" in flags

            msg = Message(
                id=str(uid),
                thread_id=thread_id,
                account_id=account_id,
                message_header_id=message_id_hdr,
                in_reply_to=in_reply_hdr,
                references=references_hdr,
                date=msg_date,
                subject=subject,
                email_from=(sender_email or "").lower(),
                sender_display_name=sender_name,
                to_display=to_disp,
                cc_display=cc_disp,
                bcc_display="",
                snippet=preview or "",
                outgoing_id=outgoing_id,
                folder_ids=[folder_name],
                is_read=is_read,
                is_starred=is_starred,
                has_attachments=False,  # Not determining atts here (legacy does it via BS outside)
                metadata={"imap_uid": uid},  # Explicit IMAP-specific identifier
            )
            messages.append(msg)

        return messages
