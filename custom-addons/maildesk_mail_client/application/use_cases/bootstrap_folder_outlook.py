# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Outlook Bootstrap Folder

Fetch newest N messages for an Outlook folder and index them into SSOT.
Transitions the folder to incremental after SSOT is populated.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Tuple

from odoo import fields

from ...adapters.outlook_adapter import OutlookAdapter
from ...domain.contracts import Message
from ...infrastructure.providers.outlook.client_factory import get_outlook_client
from ...infrastructure.providers.outlook.list_provider import outlook_resolve_folder_id

_logger = logging.getLogger(__name__)


class BootstrapFolderOutlook:
    """
    Bootstrap an Outlook folder by indexing the newest N messages into SSOT.

    Mirrors IMAP/Gmail bootstrap invariants:
    - Folder becomes incremental only after SSOT has rows.
    - Backfill remains pending unless folder is empty.
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
        if not account.is_outlook:
            return {"ok": False, "reason": "not_outlook"}

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

        sess, base_url = get_outlook_client(self.env, account)
        if not sess or not base_url:
            return {"ok": False, "reason": "outlook_session_failed"}

        folder_name = folder.imap_name or folder.name or "Inbox"
        folder_graph_id = self._resolve_folder_graph_id(
            sess, base_url, folder, folder_name
        )
        if not folder_graph_id:
            _logger.error(
                "[Outlook Bootstrap] folder id not resolved for folder=%s (account=%s)",
                folder_name,
                account.id,
            )
            return {"ok": False, "reason": "folder_id_missing"}

        msg_ids, next_link = self._list_message_ids(
            sess, base_url, folder_graph_id, limit=bootstrap_max
        )
        total_estimate = self._folder_total(sess, base_url, folder_graph_id)

        if not msg_ids:
            if total_estimate:
                _logger.error(
                    "[Outlook Bootstrap] CRITICAL: folder=%s (account=%s) "
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
                "[Outlook Bootstrap] folder=%s empty, → incremental",
                folder.id,
            )
            return {"ok": True, "mode": "empty", "fetched": 0}

        messages = self._fetch_messages(sess, base_url, account, folder_name, msg_ids)
        if not messages:
            _logger.error(
                "[Outlook Bootstrap] CRITICAL: folder=%s (account=%s) "
                "fetched 0 messages. NOT transitioning to incremental.",
                folder_name,
                account.id,
            )
            return {"ok": False, "reason": "fetch_failed", "fetched": 0}

        indexed_count = self._upsert_only(account, folder_name, messages)
        fetched_count = len(messages)

        if fetched_count > 0 and indexed_count == 0:
            _logger.error(
                "[Outlook Bootstrap] CRITICAL: folder=%s (account=%s) "
                "fetched %s messages but indexed 0.",
                folder_name,
                account.id,
                fetched_count,
            )
            return {"ok": False, "reason": "index_failed", "fetched": fetched_count}

        if indexed_count < fetched_count:
            _logger.warning(
                "[Outlook Bootstrap] folder=%s partial index failure (%s/%s succeeded)",
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
        if "outlook_backfill_next_link" in folder._fields:
            vals["outlook_backfill_next_link"] = next_link or ""
        if "outlook_graph_id" in folder._fields:
            vals["outlook_graph_id"] = folder_graph_id or ""
        if total_estimate and fetched_count >= total_estimate:
            vals["backfill_completed_at"] = fields.Datetime.now()

        folder.write(vals)

        _logger.info(
            "[Outlook Bootstrap] folder=%s fetched=%s indexed=%s → incremental",
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
            "[Outlook Bootstrap] from_now_on mode: folder %s → incremental", folder.id
        )
        return {"ok": True, "mode": "from_now_on", "fetched": 0}

    def _resolve_folder_graph_id(self, sess, base_url, folder, folder_name: str) -> str:
        graph_id = getattr(folder, "outlook_graph_id", None) or ""
        if graph_id:
            return graph_id
        resolved = outlook_resolve_folder_id(self.env, sess, base_url, folder_name)
        if resolved:
            try:
                folder.write({"outlook_graph_id": resolved})
            except Exception:
                pass
        return resolved or ""

    def _list_message_ids(
        self, sess, base_url: str, folder_graph_id: str, limit: int
    ) -> Tuple[List[str], Optional[str]]:
        ids: List[str] = []
        url = (
            f"{base_url}/me/mailFolders/{folder_graph_id}/messages"
            "?$select=id&$orderby=receivedDateTime desc&$top=50"
        )
        next_link = None
        while url and len(ids) < limit:
            r = sess.get(url, timeout=30)
            r.raise_for_status()
            data = r.json() or {}
            batch = [m.get("id") for m in data.get("value", []) if m.get("id")]
            ids.extend(batch)
            next_link = data.get("@odata.nextLink")
            if not next_link or not batch:
                break
            url = next_link
        return ids[:limit], next_link

    def _folder_total(self, sess, base_url: str, folder_graph_id: str) -> int:
        url = f"{base_url}/me/mailFolders/{folder_graph_id}?$select=totalItemCount"
        try:
            r = sess.get(url, timeout=15)
            if r.status_code == 200:
                return int(r.json().get("totalItemCount") or 0)
        except Exception:
            return 0
        return 0

    def _fetch_messages(
        self,
        sess,
        base_url: str,
        account,
        folder_name: str,
        message_ids: Iterable[str],
    ) -> List[Message]:
        ids = [str(x) for x in message_ids if x]
        if not ids:
            return []
        adapter = OutlookAdapter(self)
        return adapter.fetch_metadata_batch(
            sess, base_url, account.id, folder_name, ids
        )

    def _flags_from_state(self, is_read: bool, is_starred: bool) -> str:
        flags = []
        if is_read:
            flags.append("\\Seen")
        if is_starred:
            flags.append("\\Flagged")
        return " ".join(flags)

    def _upsert_only(self, account, folder_name: str, messages: List[Message]) -> int:
        Index = self.env["maildesk.message_index"].sudo()

        upserted = 0
        for msg in messages:
            flags = self._flags_from_state(msg.is_read, msg.is_starred)
            index_id = Index.upsert_one(
                {
                    "account_id": account.id,
                    "provider": "outlook",
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
