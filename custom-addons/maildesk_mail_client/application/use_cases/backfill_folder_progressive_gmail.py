# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Gmail Progressive Backfill Worker

Background worker for fetching older Gmail messages in controlled batches.
Respects time budgets and message caps, indexing into SSOT only.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Iterable, List, Optional

from odoo import fields

from ...adapters.gmail_adapter import GmailAdapter
from ...domain.contracts import Message
from ...infrastructure.providers.gmail.auth import gmail_build_service
from ...infrastructure.providers.gmail.label_resolver import resolve_gmail_label
from ...infrastructure.utils.folder_keys import is_all_mail_folder
from ...infrastructure.utils.email_utils import decode_header_value, parse_sender_header

_logger = logging.getLogger(__name__)


class BackfillFolderProgressiveGmail:
    """
    Progressive backfill for Gmail folders (labels) in budget-controlled slices.

    Invariants mirrored from IMAP:
    - Bounded work per run
    - Cursor persists on folder for resumable paging
    - SSOT upsert only (no ingestion queue)
    """

    def __init__(self, env):
        self.env = env
        self.start_time = None

    def execute(self, folder_id: int) -> dict:
        self.start_time = time.time()

        folder = self.env["mailbox.folder"].sudo().browse(folder_id)
        if not folder.exists():
            return {"ok": False, "reason": "folder_not_found"}

        if folder.sync_state != "incremental":
            return {"ok": False, "reason": "not_incremental"}

        if folder.backfill_completed_at:
            return {"ok": False, "reason": "already_complete"}

        account = folder.account_id
        if not account.is_gmail:
            return {"ok": False, "reason": "not_gmail"}

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

        if max_total > 0 and folder.backfill_fetched_count >= max_total:
            folder.write({"backfill_completed_at": fields.Datetime.now()})
            _logger.info(
                "[Gmail Backfill] Folder %s capped at %s messages",
                folder.id,
                folder.backfill_fetched_count,
            )
            return {"ok": True, "complete": True, "capped": True, "fetched": 0}

        folder_name = folder.imap_name or folder.name or "ALL_MAIL"
        service = gmail_build_service(account)

        label_id, label_name = resolve_gmail_label(
            service, folder, folder_name=folder_name
        )
        if not label_id and not self._is_all_mail(folder_name):
            _logger.error(
                "[Gmail Backfill] label not found for folder=%s (account=%s)",
                folder_name,
                account.id,
            )
            return {"ok": False, "reason": "label_not_found"}

        total_estimate = self._label_total(service, label_id) if label_id else 0
        page_token = (
            folder.gmail_backfill_page_token
            if "gmail_backfill_page_token" in folder._fields
            else ""
        )

        total_fetched = 0
        while True:
            elapsed = time.time() - self.start_time
            if elapsed >= job_budget:
                _logger.info(
                    "[Gmail Backfill] Folder %s budget exhausted (%.1fs)",
                    folder.id,
                    elapsed,
                )
                break

            if (
                max_total > 0
                and (folder.backfill_fetched_count + total_fetched) >= max_total
            ):
                _logger.info("[Gmail Backfill] Folder %s cap reached", folder.id)
                folder.write({"backfill_completed_at": fields.Datetime.now()})
                break

            resp = self._list_message_ids(
                service,
                label_id=label_id,
                folder_name=folder_name,
                page_token=page_token or None,
                limit=batch_size,
            )
            msg_ids = resp.get("ids") or []
            next_token = resp.get("next_token") or ""

            if not msg_ids:
                if not next_token:
                    folder.write({"backfill_completed_at": fields.Datetime.now()})
                    _logger.info(
                        "[Gmail Backfill] Folder %s complete (no more pages)",
                        folder.id,
                    )
                    break
                _logger.warning(
                    "[Gmail Backfill] Folder %s page returned 0 ids, advancing token",
                    folder.id,
                )
                page_token = next_token
                if "gmail_backfill_page_token" in folder._fields:
                    folder.write({"gmail_backfill_page_token": next_token})
                continue

            messages = self._fetch_messages(service, account, folder_name, msg_ids)
            if not messages:
                _logger.error(
                    "[Gmail Backfill] Folder %s failed to fetch message metadata",
                    folder.id,
                )
                break

            indexed = self._upsert_only(account, folder_name, messages)
            if indexed == 0:
                _logger.error(
                    "[Gmail Backfill] Folder %s index failed (0/%s)",
                    folder.id,
                    len(messages),
                )
                break

            total_fetched += len(messages)

            vals = {
                "backfill_fetched_count": folder.backfill_fetched_count + len(messages),
            }
            if total_estimate and not folder.backfill_total_estimate:
                vals["backfill_total_estimate"] = total_estimate
            if "gmail_backfill_page_token" in folder._fields:
                vals["gmail_backfill_page_token"] = next_token
            if "gmail_label_id" in folder._fields:
                vals["gmail_label_id"] = label_id or ""

            if not next_token:
                vals["backfill_completed_at"] = fields.Datetime.now()

            folder.write(vals)

            if not next_token:
                break

            page_token = next_token

        return {
            "ok": True,
            "fetched": total_fetched,
            "complete": folder.backfill_completed_at is not False,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_messages(
        self, service, account, folder_name: str, message_ids: Iterable[str]
    ) -> List[Message]:
        ids = [str(x) for x in message_ids if x]
        if not ids:
            return []

        class Facade:
            def _decode_header_value(self, h):
                return decode_header_value(h)

            def _parse_sender_header(self, h):
                return parse_sender_header(h)

        adapter = GmailAdapter(Facade())
        return adapter.fetch_metadata_batch(service, account.id, folder_name, ids)

    def _upsert_only(self, account, folder_name: str, messages: List[Message]) -> int:
        Index = self.env["maildesk.message_index"].sudo()

        upserted = 0
        for msg in messages:
            flags = self._flags_from_state(msg.is_read, msg.is_starred)
            index_id = Index.upsert_one(
                {
                    "account_id": account.id,
                    "provider": "gmail",
                    "folder": folder_name,
                    "uid": str(msg.id),
                    "message_id": msg.message_header_id,
                    "outgoing_id": msg.outgoing_id,
                    "from_addr": msg.email_from,
                    "to_addrs": msg.to_display,
                    "cc_addrs": msg.cc_display,
                    "bcc_addrs": msg.bcc_display,
                    "subject": msg.subject,
                    "date": msg.date,
                    "sender_display_name": msg.sender_display_name,
                    "preview": msg.snippet,
                    "has_attachments": msg.has_attachments,
                    "is_read": msg.is_read,
                    "is_starred": msg.is_starred,
                    "flags": flags,
                    "in_reply_to": msg.in_reply_to,
                    "references_hdr": msg.references,
                    "thread_id": msg.thread_id,
                }
            )
            if index_id:
                upserted += 1

        return upserted

    def _list_message_ids(
        self,
        service,
        *,
        label_id: Optional[str],
        folder_name: str,
        page_token: Optional[str],
        limit: int,
    ) -> Dict[str, Optional[str]]:
        if self._is_all_mail(folder_name):
            resp = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q="-in:trash -in:spam",
                    maxResults=limit,
                    pageToken=page_token,
                    fields="nextPageToken,messages/id",
                )
                .execute()
            )
        else:
            resp = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=[label_id],
                    maxResults=limit,
                    pageToken=page_token,
                    fields="nextPageToken,messages/id",
                )
                .execute()
            )
        ids = [m["id"] for m in (resp.get("messages") or [])]
        return {"ids": ids, "next_token": resp.get("nextPageToken")}

    def _label_total(self, service, label_id: Optional[str]) -> int:
        if not label_id:
            return 0
        try:
            label = service.users().labels().get(userId="me", id=label_id).execute()
            return int(label.get("messagesTotal") or 0)
        except Exception:
            return 0

    def _is_all_mail(self, folder_name: str) -> bool:
        return is_all_mail_folder(folder_name)

    def _flags_from_state(self, is_read: bool, is_starred: bool) -> str:
        flags = []
        if is_read:
            flags.append("\\Seen")
        if is_starred:
            flags.append("\\Flagged")
        return " ".join(flags)
