# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Gmail Bootstrap Folder

Fast bootstrap: fetch newest N messages for a Gmail folder (label) to make it
immediately usable via SSOT, then transition to incremental state. Older
history is handled by progressive backfill.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Tuple

from odoo import fields

from ...adapters.gmail_adapter import GmailAdapter
from ...domain.contracts import Message
from ...infrastructure.providers.gmail.auth import gmail_build_service
from ...infrastructure.providers.gmail.label_resolver import resolve_gmail_label
from ...infrastructure.utils.folder_keys import is_all_mail_folder
from ...infrastructure.utils.email_utils import decode_header_value, parse_sender_header

_logger = logging.getLogger(__name__)


class BootstrapFolderGmail:
    """
    Bootstrap a Gmail folder by indexing the newest N messages into SSOT.

    Invariants mirrored from IMAP bootstrap:
    - Folder becomes incremental only after SSOT has list-view rows.
    - Backfill remains pending (unless folder is empty).
    """

    def __init__(self, env):
        self.env = env

    def execute(self, folder_id: int) -> dict:
        Folder = self.env["mailbox.folder"].sudo()
        folder = Folder.browse(folder_id)
        if not folder.exists():
            return {"ok": False, "reason": "folder_not_found"}

        if folder.sync_state != "backfill_pending":
            return {
                "ok": False,
                "reason": "not_pending",
                "sync_state": folder.sync_state,
            }

        account = folder.account_id
        if not account.is_gmail:
            return {"ok": False, "reason": "not_gmail"}

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
        if backfill_mode == "from_now_on":
            return self._from_now_on_mode(folder)

        folder_name = folder.imap_name or folder.name or "ALL_MAIL"
        service = gmail_build_service(account)

        label_id, label_name = resolve_gmail_label(
            service, folder, folder_name=folder_name
        )
        if not label_id and not self._is_all_mail(folder_name):
            _logger.error(
                "[Gmail Bootstrap] label not found for folder=%s (account=%s)",
                folder_name,
                account.id,
            )
            return {"ok": False, "reason": "label_not_found"}

        msg_ids, next_page = self._list_message_ids(
            service, label_id=label_id, limit=bootstrap_max, folder_name=folder_name
        )
        total_estimate = self._label_total(service, label_id) if label_id else 0

        if not msg_ids:
            if total_estimate:
                _logger.error(
                    "[Gmail Bootstrap] CRITICAL: folder=%s (account=%s) "
                    "has total=%s but list returned 0 ids",
                    folder_name,
                    account.id,
                    total_estimate,
                )
                return {"ok": False, "reason": "fetch_failed", "fetched": 0}

            folder.write(
                {
                    "sync_state": "incremental",
                    "last_uid": 0,
                    "backfill_last_uid": 0,
                    "backfill_completed_at": fields.Datetime.now(),
                    "backfill_fetched_count": 0,
                    "backfill_total_estimate": 0,
                }
            )
            _logger.info(
                "[Gmail Bootstrap] folder=%s empty, → incremental",
                folder.id,
            )
            return {"ok": True, "mode": "empty", "fetched": 0}

        messages = self._fetch_messages(service, account, folder_name, msg_ids)
        if not messages:
            _logger.error(
                "[Gmail Bootstrap] CRITICAL: folder=%s (account=%s) "
                "fetched 0 messages. NOT transitioning to incremental.",
                folder_name,
                account.id,
            )
            return {"ok": False, "reason": "fetch_failed", "fetched": 0}

        indexed_count = self._upsert_only(account, folder_name, messages)
        fetched_count = len(messages)

        if fetched_count > 0 and indexed_count == 0:
            _logger.error(
                "[Gmail Bootstrap] CRITICAL: folder=%s (account=%s) "
                "fetched %s messages but indexed 0.",
                folder_name,
                account.id,
                fetched_count,
            )
            return {"ok": False, "reason": "index_failed", "fetched": fetched_count}

        if indexed_count < fetched_count:
            _logger.warning(
                "[Gmail Bootstrap] folder=%s partial index failure (%s/%s succeeded)",
                folder_name,
                indexed_count,
                fetched_count,
            )

        vals = {
            "sync_state": "incremental",
            "last_uid": 0,
            "backfill_last_uid": 0,
            "backfill_started_at": fields.Datetime.now(),
            "backfill_fetched_count": fetched_count,
            "backfill_total_estimate": int(total_estimate or 0),
        }

        # Optional provider cursor fields (only if present on model)
        if "gmail_label_id" in folder._fields:
            vals["gmail_label_id"] = label_id or ""
        if "gmail_backfill_page_token" in folder._fields:
            vals["gmail_backfill_page_token"] = next_page or ""

        if total_estimate and fetched_count >= total_estimate:
            vals["backfill_completed_at"] = fields.Datetime.now()

        folder.write(vals)

        _logger.info(
            "[Gmail Bootstrap] folder=%s fetched=%s indexed=%s → incremental",
            folder.id,
            fetched_count,
            indexed_count,
        )
        return {"ok": True, "mode": "bootstrap", "fetched": fetched_count}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _from_now_on_mode(self, folder) -> dict:
        folder.write(
            {
                "sync_state": "incremental",
                "last_uid": 0,
                "backfill_last_uid": 0,
                "backfill_completed_at": fields.Datetime.now(),
                "backfill_fetched_count": 0,
                "backfill_total_estimate": 0,
            }
        )
        _logger.info(
            "[Gmail Bootstrap] from_now_on mode: folder %s → incremental", folder.id
        )
        return {"ok": True, "mode": "from_now_on", "fetched": 0}

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
        limit: int,
        folder_name: str,
    ) -> Tuple[List[str], Optional[str]]:
        msg_ids: List[str] = []
        page_token = None

        while True:
            if self._is_all_mail(folder_name):
                resp = (
                    service.users()
                    .messages()
                    .list(
                        userId="me",
                        q="-in:trash -in:spam",
                        maxResults=500,
                        pageToken=page_token,
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
                        maxResults=500,
                        pageToken=page_token,
                    )
                    .execute()
                )

            msg_ids.extend([m["id"] for m in (resp.get("messages") or [])])
            if len(msg_ids) >= limit:
                msg_ids = msg_ids[:limit]
                return msg_ids, resp.get("nextPageToken")

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return msg_ids, None

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
