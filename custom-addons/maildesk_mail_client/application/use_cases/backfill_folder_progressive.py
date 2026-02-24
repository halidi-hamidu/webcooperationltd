# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Progressive Backfill Worker - Phase 5.2

Background worker for fetching older messages in controlled batches.
Respects time budgets, message caps, and uses ingest queue.

ARCHITECTURE:
- APPLICATION SERVICE layer
- Works on folders in 'incremental' state with incomplete backfill
- Uses backfill_last_uid to track progress
- Stops when: budget exhausted, cap reached, or UID 1 reached

INVARIANTS:
- Never blocks RPC (all work via ingest queue)
- Respects job_budget_seconds (default 25s)
- Respects max_total_per_folder cap (default 20k)
- Updates backfill_last_uid after each batch
"""

import logging
import re
import time
from email.utils import parsedate_to_datetime

from odoo import fields

from ...application.services.display_formatting import compute_sender_display_name
from ...application.services.imap_client_service import build_authenticated_imap_client
from ...infrastructure.utils.mime_decoder import (
    decode_mime_header,
    decode_address_display_name,
)

_logger = logging.getLogger(__name__)


class BackfillFolderProgressive:
    """
    Progressive backfill: fetch older messages in budget-controlled slices.

    Strategy:
    1. Find folders in 'incremental' state with backfill_last_uid > 1
    2. Fetch UIDs from backfill_last_uid down to 1 in batches
    3. Enqueue to ingest_queue (non-blocking)
    4. Update backfill_last_uid after each batch
    5. Stop when budget exhausted or UID 1 reached
    """

    def __init__(self, env):
        self.env = env
        self.start_time = None

    def execute(self, folder_id: int) -> dict:
        """
        Run one progressive backfill slice for a folder.

        Returns:
            dict with ok, fetched, backfill_last_uid, complete
        """
        self.start_time = time.time()

        folder = self.env["mailbox.folder"].sudo().browse(folder_id)

        if not folder.exists():
            return {"ok": False, "reason": "folder_not_found"}

        # Guard: Only backfill if incremental and not complete
        if folder.sync_state != "incremental":
            return {"ok": False, "reason": "not_incremental"}

        if folder.backfill_completed_at:
            return {"ok": False, "reason": "already_complete"}

        if folder.backfill_last_uid <= 1:
            # Complete!
            folder.write({"backfill_completed_at": fields.Datetime.now()})
            _logger.info(f"[Backfill] Folder {folder.id} complete (UID 1 reached)")
            return {"ok": True, "complete": True, "fetched": 0}

        # Get configuration
        batch_size = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("maildesk.backfill_batch_size", "100")
        )
        job_budget = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("maildesk.backfill_job_budget_seconds", "25")
        )
        max_total = int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("maildesk.backfill_max_total_per_folder", "20000")
        )

        # Check cap
        if max_total > 0 and folder.backfill_fetched_count >= max_total:
            folder.write({"backfill_completed_at": fields.Datetime.now()})
            _logger.info(
                f"[Backfill] Folder {folder.id} capped at {folder.backfill_fetched_count} messages"
            )
            return {"ok": True, "complete": True, "capped": True, "fetched": 0}

        # Provider-specific backfill
        account = folder.account_id
        if account.is_gmail:
            return self._backfill_gmail(folder, batch_size, job_budget, max_total)
        else:
            return self._backfill_imap(folder, batch_size, job_budget, max_total)

    def _backfill_imap(self, folder, batch_size, job_budget, max_total) -> dict:
        """Progressive backfill for IMAP folder."""
        account = folder.account_id
        total_fetched = 0

        with build_authenticated_imap_client(self.env, account) as client:
            folder_name = folder.imap_name or folder.name or "INBOX"
            client.select_folder(folder_name, readonly=True)

            current_uid = folder.backfill_last_uid

            while current_uid > 0:
                # Budget check
                elapsed = time.time() - self.start_time
                if elapsed >= job_budget:
                    _logger.info(
                        f"[Backfill] Folder {folder.id} budget exhausted ({elapsed:.1f}s)"
                    )
                    break

                # Cap check
                if (
                    max_total > 0
                    and (folder.backfill_fetched_count + total_fetched) >= max_total
                ):
                    _logger.info(f"[Backfill] Folder {folder.id} cap reached")
                    folder.write({"backfill_completed_at": fields.Datetime.now()})
                    break

                # Calculate batch
                batch_end = current_uid
                batch_start = max(1, batch_end - batch_size + 1)
                uids = list(range(batch_start, batch_end + 1))

                # Fetch messages
                messages = self._fetch_imap_messages(client, folder_name, account, uids)

                # CRITICAL FIX F.2: Track ACTUAL fetched UIDs, not batch range
                # If partial fetch (e.g., 50/100), only advance to lowest successfully fetched UID - 1
                fetched_uids = [msg["uid"] for msg in messages] if messages else []

                if messages:
                    self._upsert_index_only(account.id, folder_name, "imap", messages)
                    total_fetched += len(messages)

                # INVARIANT: Cursor advances ONLY to (min_fetched_uid - 1)
                # This ensures unfetched UIDs are retried on next run
                if fetched_uids:
                    min_fetched_uid = min(fetched_uids)
                    new_backfill_last_uid = min_fetched_uid - 1
                else:
                    # No UIDs fetched in this batch → retry same range next time
                    # Don't advance cursor at all
                    _logger.info(
                        f"[Backfill] Folder {folder.id} batch {batch_start}-{batch_end} returned 0 UIDs, retrying"
                    )
                    break  # Exit to avoid infinite loop, next cron will retry

                # Update progress
                folder.write(
                    {
                        "backfill_last_uid": new_backfill_last_uid,
                        "backfill_fetched_count": folder.backfill_fetched_count
                        + len(messages),
                    }
                )

                current_uid = new_backfill_last_uid

                if current_uid <= 0:
                    # Complete!
                    folder.write({"backfill_completed_at": fields.Datetime.now()})
                    _logger.info(
                        f"[Backfill] Folder {folder.id} complete (UID 1 reached)"
                    )
                    break

        return {
            "ok": True,
            "fetched": total_fetched,
            "backfill_last_uid": folder.backfill_last_uid,
            "complete": folder.backfill_completed_at is not False,
        }

    def _backfill_gmail(self, folder, batch_size, job_budget, max_total) -> dict:
        """Progressive backfill for Gmail (placeholder - uses rebuild)."""
        # Gmail: Mark as complete (rebuild handles it)
        folder.write({"backfill_completed_at": fields.Datetime.now()})
        return {"ok": True, "complete": True, "gmail": True}

    def _fetch_imap_messages(self, client, folder_name, account, uids: list) -> list:
        """Fetch SSOT list-view metadata for progressive backfill (no ingestion)."""
        if not uids:
            return []

        try:
            fetch_data = client.fetch(
                uids,
                [
                    "UID",
                    "FLAGS",
                    "INTERNALDATE",
                    "ENVELOPE",
                    "RFC822.SIZE",
                    "BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)]",
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
                parsed = self._parse_envelope(
                    envelope, flags, internal_date, header_fields
                )
                parsed["uid"] = uid
                parsed["size"] = data.get(b"RFC822.SIZE", 0)
                messages.append(parsed)

            return messages
        except Exception as e:
            _logger.error(f"[Backfill] Failed to fetch UIDs {uids[:5]}...: {e}")
            return []

    def _upsert_index_only(
        self, account_id: int, folder_name: str, provider: str, messages: list
    ) -> int:
        """Upsert SSOT rows only (no queue, no routing, no Odoo mail import)."""
        Index = self.env["maildesk.message_index"].sudo()
        upserted = 0

        for msg in messages:
            index_id = Index.upsert_one(
                {
                    "account_id": account_id,
                    "provider": provider,
                    "folder": folder_name,
                    "uid": str(msg["uid"]),
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
                }
            )
            if index_id:
                upserted += 1

        _logger.info(
            f"[Backfill] Upserted {upserted}/{len(messages)} to SSOT (folder={folder_name})"
        )
        return upserted

    def _parse_envelope(self, envelope, flags, internal_date, header_fields):
        """Parse IMAP ENVELOPE + FLAGS (imapclient returns objects, not tuples)."""
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

        # Use attribute access (env.subject, env.from_, etc) with MIME decoding
        subject = envelope.subject
        result["subject"] = decode_mime_header(subject) if subject else "(No Subject)"
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
        result["to_addrs"] = (
            self._format_address_list(envelope.to) if envelope.to else ""
        )
        result["cc_addrs"] = (
            self._format_address_list(envelope.cc) if envelope.cc else ""
        )
        result["bcc_addrs"] = (
            self._format_address_list(envelope.bcc) if envelope.bcc else ""
        )
        if envelope.date:
            try:
                date_str = self._decode_bytes(envelope.date)
                result["date"] = parsedate_to_datetime(date_str)
            except Exception:
                result["date"] = internal_date
        else:
            result["date"] = internal_date
        header_str = (
            header_fields.decode("utf-8", errors="ignore") if header_fields else ""
        )
        result["message_id"] = self._extract_header(header_str, "Message-ID")
        result["in_reply_to"] = self._extract_header(header_str, "In-Reply-To")
        result["references_hdr"] = self._extract_header(header_str, "References")
        flags_list = [self._decode_bytes(f) for f in flags]
        result["is_read"] = "\\Seen" in flags_list or b"\\Seen" in flags
        result["is_starred"] = "\\Flagged" in flags_list or b"\\Flagged" in flags
        result["flags"] = ",".join(flags_list)
        result["preview"] = result["subject"][:200] if result.get("subject") else ""
        result["has_attachments"] = False
        return result

    def _decode_bytes(self, value):
        """Safely decode bytes to string."""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
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

    def _upsert_index_and_enqueue(
        self,
        account_id: int,
        folder_id: int,
        folder_name: str,
        provider: str,
        messages: list,
    ) -> int:
        """Deprecated in v3 safety model (kept for backward compatibility)."""
        return self._upsert_index_only(account_id, folder_name, provider, messages)
