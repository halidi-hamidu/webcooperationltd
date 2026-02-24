# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Bootstrap Folder - Phase 5.2

Fast bootstrap: fetch newest N messages to make folder immediately usable.
Sets incremental state (new messages handled) and backfill_last_uid (for progressive backfill).

ARCHITECTURE:
- APPLICATION SERVICE layer
- Calls infrastructure adapters for IMAP/Gmail
- Uses ingest queue for non-blocking ingestion
- No ORM access (uses repos where needed)

INVARIANTS:
- last_uid set to UIDNEXT-1 (incremental sync works immediately)
- backfill_last_uid set to oldest_bootstrap_uid - 1 (progressive continues older)
- sync_state = 'incremental' (folder usable)
- backfill may still be in progress (tracked by backfill_completed_at)
"""

import logging
import re
from email.utils import parsedate_to_datetime

from odoo import fields

from ...application.services.display_formatting import compute_sender_display_name
from ...application.services.imap_client_service import build_authenticated_imap_client
from ...infrastructure.providers.imap.utils import has_attachments_from_bodystructure
from ...infrastructure.rendering.preview_extractor import (
    MAX_PREVIEW_BYTES,
    extract_imap_preview,
)
from ...infrastructure.utils.imap_fetch import pick_imap_body_bytes
from ...infrastructure.utils.mime_decoder import (
    decode_mime_header,
    decode_address_display_name,
)

_logger = logging.getLogger(__name__)


class BootstrapFolder:
    """
    Bootstrap folder with newest N messages for instant usability.

    Strategy:
    1. Fetch newest X messages (from UIDNEXT backward)
    2. Enqueue to ingest_queue
    3. Set last_uid = UIDNEXT-1 (incremental works)
    4. Set backfill_last_uid = oldest_fetched - 1 (progressive continues)
    5. Transition to 'incremental' state
    """

    def __init__(self, env):
        self.env = env

    def execute(self, folder_id: int) -> dict:
        """
        Bootstrap a folder in backfill_pending state.

        Returns:
            dict with ok, mode, fetched_count, last_uid, backfill_last_uid
        """
        Folder = self.env["mailbox.folder"].sudo()
        folder = Folder.browse(folder_id)

        if not folder.exists():
            return {"ok": False, "reason": "folder_not_found"}

        # Guard: Only bootstrap if pending
        if folder.sync_state != "backfill_pending":
            return {
                "ok": False,
                "reason": "not_pending",
                "sync_state": folder.sync_state,
            }

        # Get configuration
        bootstrap_max = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("maildesk.backfill_bootstrap_max", "1500")
        )

        backfill_mode = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("maildesk.backfill_mode", "progressive")
        )

        # Handle from_now_on mode
        if backfill_mode == "from_now_on":
            return self._from_now_on_mode(folder)

        # Provider-specific bootstrap
        account = folder.account_id
        if account.is_gmail:
            return self._bootstrap_gmail(folder, bootstrap_max)
        else:
            return self._bootstrap_imap(folder, bootstrap_max)

    def _from_now_on_mode(self, folder) -> dict:
        """Set folder to incremental with no backfill (from-now-on mode)."""
        # Need UIDNEXT to set last_uid
        account = folder.account_id

        with build_authenticated_imap_client(self.env, account) as client:
            folder_name = folder.imap_name or folder.name or "INBOX"
            res = client.select_folder(folder_name, readonly=True) or {}
            uidnext = int(res.get(b"UIDNEXT", 1) or res.get("UIDNEXT", 1))

        folder.write(
            {
                "sync_state": "incremental",
                "last_uid": max(uidnext - 1, 0),
                "backfill_last_uid": 0,  # No more backfill
                "backfill_completed_at": fields.Datetime.now(),
                "backfill_fetched_count": 0,
            }
        )

        _logger.info(
            f"[Bootstrap] from_now_on mode: folder {folder.id} → incremental (no backfill)"
        )
        return {"ok": True, "mode": "from_now_on", "fetched": 0}

    def _bootstrap_imap(self, folder, bootstrap_max: int) -> dict:
        """Bootstrap IMAP folder with newest N messages."""
        account = folder.account_id

        with build_authenticated_imap_client(self.env, account) as client:
            folder_name = folder.imap_name or folder.name or "INBOX"
            res = client.select_folder(folder_name, readonly=True) or {}
            uidnext = int(res.get(b"UIDNEXT", 1) or res.get("UIDNEXT", 1))
            exists = int(
                res.get(b"EXISTS", 0) or res.get("EXISTS", 0)
            )  # Real message count

            if uidnext <= 1 or exists == 0:
                # Empty folder (or emptied history where UIDNEXT is still > 1).
                folder.write(
                    {
                        "sync_state": "incremental",
                        "last_uid": 0,
                        "backfill_last_uid": 0,
                        "backfill_completed_at": fields.Datetime.now(),
                        "backfill_fetched_count": 0,
                    }
                )
                _logger.info(
                    f"[Bootstrap] IMAP folder {folder.id} empty, → incremental"
                )
                return {"ok": True, "mode": "empty", "fetched": 0}

            # UIDNEXT can remain high even when a folder is empty (all messages deleted).
            # In that case, `EXISTS` is the source of truth: if it is zero, there is
            # nothing to backfill and the folder should immediately transition to
            # incremental without getting stuck in backfill_pending.
            if exists <= 0:
                end_uid = max(uidnext - 1, 0)
                folder.write(
                    {
                        "sync_state": "incremental",
                        "last_uid": end_uid,
                        "backfill_last_uid": 0,
                        "backfill_completed_at": fields.Datetime.now(),
                        "backfill_fetched_count": 0,
                        "backfill_total_estimate": 0,
                    }
                )
                _logger.info(
                    f"[Bootstrap] IMAP folder {folder.id} ({folder.name}) empty (EXISTS=0, UIDNEXT={uidnext}), → incremental"
                )
                return {"ok": True, "mode": "empty", "fetched": 0}

            # Calculate UID range: fetch newest bootstrap_max messages
            end_uid = uidnext - 1
            start_uid = max(1, end_uid - bootstrap_max + 1)

            _logger.info(
                f"[Bootstrap] IMAP folder {folder.id}: fetching UIDs {start_uid}-{end_uid} (newest {bootstrap_max})"
            )

            # Fetch messages in batches
            batch_size = 100
            fetched_count = 0
            indexed_count = 0  # SSOT rows written

            for batch_start in range(start_uid, end_uid + 1, batch_size):
                batch_end = min(batch_start + batch_size - 1, end_uid)
                uids = list(range(batch_start, batch_end + 1))

                # Fetch and upsert to SSOT
                messages = self._fetch_imap_messages(client, folder_name, account, uids)
                if messages:
                    indexed = self._upsert_index_only(
                        account.id, folder.id, folder_name, "imap", messages
                    )
                    fetched_count += len(messages)
                    indexed_count += indexed

            # CRITICAL: Prevent state corruption if fetch failed completely
            if fetched_count == 0:
                _logger.warning(
                    f"[Bootstrap] Folder {folder.id} ({folder.name}): "
                    f"bootstrap fetch returned 0 messages (EXISTS={exists}, UIDNEXT={uidnext}); "
                    f"remaining in backfill_pending."
                )
                return {
                    "ok": False,
                    "reason": "fetch_failed",
                    "fetched": 0,
                    "enqueued": 0,
                }

            if indexed_count == 0:
                _logger.error(
                    f"[Bootstrap] Folder {folder.id} ({folder.name}): "
                    f"fetched {fetched_count} messages but indexed 0. "
                    f"NOT transitioning to incremental. Check logs for upsert failures."
                )
                return {"ok": False, "reason": "index_failed", "fetched": fetched_count}

            # Update folder state
            folder.write(
                {
                    "sync_state": "incremental",
                    "last_uid": end_uid,
                    "backfill_last_uid": start_uid
                    - 1,  # Progressive continues from here
                    "backfill_started_at": fields.Datetime.now(),
                    "backfill_fetched_count": fetched_count,
                    "backfill_total_estimate": exists,  # Real message count, not UIDNEXT
                }
            )

            _logger.info(
                f"[Bootstrap] IMAP folder {folder.id}: {fetched_count} messages fetched, "
                f"{indexed_count} indexed → incremental, "
                f"backfill_last_uid={start_uid - 1} (progressive will fetch older)"
            )

            return {
                "ok": True,
                "mode": "bootstrap",
                "fetched": fetched_count,
                "last_uid": end_uid,
                "backfill_last_uid": start_uid - 1,
            }

    def _bootstrap_gmail(self, folder, bootstrap_max: int) -> dict:
        """Bootstrap Gmail folder (placeholder - reuse existing rebuild logic)."""
        # Gmail: Use existing SyncGmailHistory._rebuild() logic
        # For now, mark as incremental and let Gmail sync handle it
        folder.write({"sync_state": "incremental", "last_uid": 0})
        _logger.info(
            f"[Bootstrap] Gmail folder {folder.id} → incremental (Gmail uses rebuild)"
        )
        return {"ok": True, "mode": "gmail_rebuild", "fetched": 0}

    def _fetch_imap_messages(self, client, folder_name, account, uids: list) -> list:
        """
        Fetch FULL message metadata from IMAP for SSOT population.

        CRITICAL: Must fetch all list-view fields during backfill.
        SSOT must be complete after backfill; ingest only handles body/attachments.
        """
        if not uids:
            return []

        try:
            # Fetch ENVELOPE + FLAGS + headers + BODYSTRUCTURE for complete SSOT
            fetch_data = client.fetch(
                uids,
                [
                    "UID",
                    "FLAGS",
                    "INTERNALDATE",
                    "ENVELOPE",
                    "RFC822.SIZE",
                    "BODYSTRUCTURE",  # CRITICAL: Required for has_attachments detection
                    "BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)]",
                    f"BODY.PEEK[]<0.{MAX_PREVIEW_BYTES}>",
                ],
            )

            messages = []
            for uid, data in fetch_data.items():
                envelope = data.get(b"ENVELOPE")
                flags = data.get(b"FLAGS", [])
                internal_date = data.get(b"INTERNALDATE")
                header_fields = data.get(
                    b"BODY[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)]", b""
                )

                body_bytes = pick_imap_body_bytes(data)

                # Extract BODYSTRUCTURE for attachment detection
                bodystructure = data.get(b"BODYSTRUCTURE")

                # Parse ENVELOPE to extract all list-view fields
                parsed = self._parse_envelope(
                    envelope,
                    flags,
                    internal_date,
                    header_fields,
                    body_bytes,
                    bodystructure,
                )
                parsed["uid"] = uid
                parsed["size"] = data.get(b"RFC822.SIZE", 0)

                messages.append(parsed)

            return messages
        except Exception as e:
            _logger.error(f"[Bootstrap] Failed to fetch UIDs {uids[:5]}...: {e}")
            return []

    def _parse_envelope(
        self,
        envelope,
        flags,
        internal_date,
        header_fields,
        body_bytes=b"",
        bodystructure=None,
    ):
        """
        Parse IMAP ENVELOPE + FLAGS into message_index fields.

        CRITICAL: imapclient returns Envelope/Address OBJECTS, not tuples.
        Must use env.subject, env.from_, env.to (NOT env[1], env[2]).
        """
        result = {}

        if not envelope:
            return {
                "subject": "(No Subject)",
                "from_addr": "",
                "sender_display_name": "",
                "to_addrs": "",
                "cc_addrs": "",
                "bcc_addrs": "",
                "date": internal_date,
                "message_id": "",
                "in_reply_to": "",
                "references_hdr": "",
                "is_read": False,
                "is_starred": False,
                "flags": "",
                "preview": "",
                "has_attachments": False,
            }

        # Extract subject (Envelope.subject attribute) with MIME decoding
        subject = envelope.subject
        result["subject"] = decode_mime_header(subject) if subject else "(No Subject)"

        # Extract preview from body_bytes if available
        if body_bytes:
            try:
                preview = self._extract_imap_preview(body_bytes, result["subject"])
                # If extraction failed or returned empty, use subject as fallback
                result["preview"] = (
                    preview if preview and preview.strip() else result["subject"]
                )
            except Exception:
                result["preview"] = result["subject"]
        else:
            # No body available - use subject
            result["preview"] = result["subject"]

        # Detect attachments from BODYSTRUCTURE
        if bodystructure:
            result["has_attachments"] = has_attachments_from_bodystructure(
                bodystructure
            )
        else:
            result["has_attachments"] = False

        # Extract from (Envelope.from_ attribute - note underscore!)
        # from_ is a list of Address objects
        from_list = envelope.from_
        if from_list and len(from_list) > 0:
            addr = from_list[0]
            result["from_addr"] = self._format_single_address(addr)

            # Use canonical service for sender display name
            result["sender_display_name"] = compute_sender_display_name(
                from_addr=result["from_addr"],
                raw_sender_name=decode_address_display_name(
                    addr.name, result["from_addr"]
                )
                if addr.name
                else None,
            )
        else:
            result["from_addr"] = ""
            result["sender_display_name"] = ""

        # Extract to, cc, bcc (all are Address lists)
        result["to_addrs"] = (
            self._format_address_list(envelope.to) if envelope.to else ""
        )
        result["cc_addrs"] = (
            self._format_address_list(envelope.cc) if envelope.cc else ""
        )
        result["bcc_addrs"] = (
            self._format_address_list(envelope.bcc) if envelope.bcc else ""
        )

        # Extract date (Envelope.date attribute)
        if envelope.date:
            try:
                date_str = self._decode_bytes(envelope.date)
                result["date"] = parsedate_to_datetime(date_str)
            except Exception:
                result["date"] = internal_date
        else:
            result["date"] = internal_date

        # Parse header fields for threading
        header_str = (
            header_fields.decode("utf-8", errors="ignore") if header_fields else ""
        )
        result["message_id"] = self._extract_header(header_str, "Message-ID")
        result["in_reply_to"] = self._extract_header(header_str, "In-Reply-To")
        result["references_hdr"] = self._extract_header(header_str, "References")

        # Extract flags (list of bytes or strings)
        flags_list = [self._decode_bytes(f) for f in flags]
        result["is_read"] = "\\Seen" in flags_list or b"\\Seen" in flags
        result["is_starred"] = "\\Flagged" in flags_list or b"\\Flagged" in flags
        result["flags"] = ",".join(flags_list)  # Store comma-separated flags string

        # Preview and has_attachments were already extracted above
        # DO NOT overwrite them!

        return result

    def _decode_bytes(self, value):
        """Safely decode bytes to string."""
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8", errors="ignore")
            except Exception:
                return ""
        return value if value else ""

    def _format_single_address(self, addr):
        """Format single Address object to email string."""
        if not addr:
            return ""
        mailbox = self._decode_bytes(addr.mailbox) if addr.mailbox else ""
        host = self._decode_bytes(addr.host) if addr.host else ""
        if mailbox and host:
            return f"{mailbox}@{host}"
        return ""

    def _format_address_list(self, addr_list):
        """Format Address list to comma-separated email strings."""
        if not addr_list:
            return ""
        addrs = []
        for addr in addr_list:
            email = self._format_single_address(addr)
            if email:
                addrs.append(email)
        return ",".join(addrs)

    def _extract_header(self, header_str, header_name):
        """Extract header value from raw header string."""
        pattern = rf"{header_name}:\s*(.+?)(?:\r?\n(?!\s)|$)"
        match = re.search(pattern, header_str, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_imap_preview(self, body_bytes, subject):
        """Extract a stable preview text from IMAP message bytes."""
        return extract_imap_preview(body_bytes, subject)

    def _upsert_index_only(
        self,
        account_id: int,
        folder_id: int,
        folder_name: str,
        provider: str,
        messages: list,
    ) -> int:
        """
        Upsert FULL message_index records (SSOT write only).

        Backfill/bootstrap must be pure indexing: it MUST NOT enqueue, route,
        or import messages into Odoo (`mail.thread.message_process`).
        """
        Index = self.env["maildesk.message_index"].sudo()
        upserted = 0

        for msg in messages:
            # Upsert FULL record into message_index (SSOT)
            index_id = Index.upsert_one(
                {
                    "account_id": account_id,
                    "provider": provider,
                    "folder": folder_name,
                    "uid": str(msg["uid"]),
                    # List-view critical fields (ALL populated during backfill)
                    "subject": msg.get("subject", "(No Subject)"),
                    "from_addr": msg.get("from_addr", ""),
                    "to_addrs": msg.get("to_addrs", ""),
                    "cc_addrs": msg.get("cc_addrs", ""),
                    "bcc_addrs": msg.get("bcc_addrs", ""),
                    "date": msg.get("date"),
                    "sender_display_name": msg.get("sender_display_name", ""),
                    "preview": msg.get("preview", ""),
                    "has_attachments": msg.get("has_attachments", False),
                    "is_read": msg.get("is_read", False),
                    "is_starred": msg.get("is_starred", False),
                    "flags": msg.get("flags", ""),
                    "message_id": msg.get("message_id"),
                    "in_reply_to": msg.get("in_reply_to"),
                    "references_hdr": msg.get("references_hdr"),
                    # thread_id computed automatically by message_index
                }
            )

            if index_id:
                upserted += 1

        _logger.info(
            f"[Bootstrap] Upserted {upserted}/{len(messages)} to SSOT (folder={folder_name})"
        )
        return upserted
