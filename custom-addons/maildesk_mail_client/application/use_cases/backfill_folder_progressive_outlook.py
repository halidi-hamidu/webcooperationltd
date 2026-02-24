# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Outlook Progressive Backfill Worker

Fetch older Outlook messages in bounded slices using Graph paging.
"""

from __future__ import annotations

import logging
import time
from typing import Iterable, List, Optional

from odoo import fields

from ...adapters.outlook_adapter import OutlookAdapter
from ...domain.contracts import Message
from ...infrastructure.providers.outlook.client_factory import get_outlook_client
from ...infrastructure.providers.outlook.list_provider import outlook_resolve_folder_id

_logger = logging.getLogger(__name__)


class BackfillFolderProgressiveOutlook:
    """
    Progressive backfill for Outlook folders in budget-controlled slices.

    Invariants mirrored from IMAP:
    - Bounded work per run
    - Resumable cursor stored on folder
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
        if not account.is_outlook:
            return {"ok": False, "reason": "not_outlook"}

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
                "[Outlook Backfill] Folder %s capped at %s messages",
                folder.id,
                folder.backfill_fetched_count,
            )
            return {"ok": True, "complete": True, "capped": True, "fetched": 0}

        sess, base_url = get_outlook_client(self.env, account)
        if not sess or not base_url:
            return {"ok": False, "reason": "outlook_session_failed"}

        folder_name = folder.imap_name or folder.name or "Inbox"
        folder_graph_id = self._resolve_folder_graph_id(
            sess, base_url, folder, folder_name
        )
        if not folder_graph_id:
            _logger.error(
                "[Outlook Backfill] folder id not resolved for folder=%s (account=%s)",
                folder_name,
                account.id,
            )
            return {"ok": False, "reason": "folder_id_missing"}

        total_estimate = self._folder_total(sess, base_url, folder_graph_id)
        next_link = (
            folder.outlook_backfill_next_link
            if "outlook_backfill_next_link" in folder._fields
            else ""
        )

        total_fetched = 0
        while True:
            elapsed = time.time() - self.start_time
            if elapsed >= job_budget:
                _logger.info(
                    "[Outlook Backfill] Folder %s budget exhausted (%.1fs)",
                    folder.id,
                    elapsed,
                )
                break

            if (
                max_total > 0
                and (folder.backfill_fetched_count + total_fetched) >= max_total
            ):
                _logger.info("[Outlook Backfill] Folder %s cap reached", folder.id)
                folder.write({"backfill_completed_at": fields.Datetime.now()})
                break

            msg_ids, next_link = self._list_message_ids(
                sess,
                base_url,
                folder_graph_id,
                limit=batch_size,
                next_link=next_link or None,
            )

            if not msg_ids:
                if not next_link:
                    folder.write({"backfill_completed_at": fields.Datetime.now()})
                    _logger.info(
                        "[Outlook Backfill] Folder %s complete (no more pages)",
                        folder.id,
                    )
                    break
                _logger.warning(
                    "[Outlook Backfill] Folder %s page returned 0 ids, advancing",
                    folder.id,
                )
                if "outlook_backfill_next_link" in folder._fields:
                    folder.write({"outlook_backfill_next_link": next_link or ""})
                continue

            messages = self._fetch_messages(
                sess, base_url, account, folder_name, msg_ids
            )
            if not messages:
                _logger.error(
                    "[Outlook Backfill] Folder %s failed to fetch message metadata",
                    folder.id,
                )
                break

            indexed = self._upsert_only(account, folder_name, messages)
            if indexed == 0:
                _logger.error(
                    "[Outlook Backfill] Folder %s index failed (0/%s)",
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
            if "outlook_backfill_next_link" in folder._fields:
                vals["outlook_backfill_next_link"] = next_link or ""
            if "outlook_graph_id" in folder._fields:
                vals["outlook_graph_id"] = folder_graph_id or ""

            if not next_link:
                vals["backfill_completed_at"] = fields.Datetime.now()

            folder.write(vals)

            if not next_link:
                break

        return {
            "ok": True,
            "fetched": total_fetched,
            "complete": folder.backfill_completed_at is not False,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
        self,
        sess,
        base_url: str,
        folder_graph_id: str,
        *,
        limit: int,
        next_link: Optional[str] = None,
    ) -> tuple[list[str], Optional[str]]:
        ids: List[str] = []
        url = next_link or (
            f"{base_url}/me/mailFolders/{folder_graph_id}/messages"
            "?$select=id&$orderby=receivedDateTime desc&$top=50"
        )
        next_cursor = None
        while url and len(ids) < limit:
            r = sess.get(url, timeout=30)
            r.raise_for_status()
            data = r.json() or {}
            batch = [m.get("id") for m in data.get("value", []) if m.get("id")]
            ids.extend(batch)
            next_cursor = data.get("@odata.nextLink")
            if not next_cursor or not batch:
                break
            url = next_cursor
        return ids[:limit], next_cursor

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
