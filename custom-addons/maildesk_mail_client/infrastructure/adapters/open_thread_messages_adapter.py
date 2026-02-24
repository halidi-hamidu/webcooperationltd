# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Open Thread Messages Adapter.

Implements infrastructure integration for Open Thread Messages Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from __future__ import annotations

from typing import Any, Dict, List

from odoo import fields

from ...application.use_cases.open_message import OpenMessage, OpenMessageParams
from ...infrastructure.adapters.open_message_adapter import OpenMessageAdapter


class OpenThreadMessagesAdapter:
    def __init__(self, env):
        self.env = env
        self._open_message_adapter = OpenMessageAdapter(env)
        self._open_message = OpenMessage(self._open_message_adapter)

    # Models / access
    def account_browse(self, account_id: int) -> Any:
        return self.env["mailbox.account"].browse(int(account_id)).exists()

    def check_account_access(self, account: Any) -> None:
        """Check user has access to account."""
        if not account.exists():
            raise ValueError("Account does not exist")
        account.check_access("read")

    # SSOT thread topology
    def get_thread_index_records(self, account: Any, thread_id: str) -> List[Any]:
        Index = self.env["maildesk.message_index"].sudo()
        return Index.search(
            [("account_id", "=", int(account.id)), ("thread_id", "=", str(thread_id))],
            order="date asc",
        )

    def folders_by_name(
        self, account_id: int, folder_names: List[str]
    ) -> Dict[str, Any]:
        if not folder_names:
            return {}
        Folder = self.env["mailbox.folder"].sudo()
        folders = Folder.search(
            [
                ("account_id", "=", int(account_id)),
                "|",
                ("imap_name", "in", folder_names),
                ("name", "in", folder_names),
            ]
        )
        out: Dict[str, Any] = {}
        for f in folders:
            if getattr(f, "imap_name", None):
                out[f.imap_name] = f
            if getattr(f, "name", None):
                out[f.name] = f
        return out

    # UI cache
    def cache_resolve_canonical_index_id(self, index_id: int) -> int:
        Cache = self.env["maildesk.ui_cache"].sudo()
        return int(Cache.resolve_canonical_index_id(int(index_id)))

    def cache_fetch_body_map(self, index_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not index_ids:
            return {}
        Cache = self.env["maildesk.ui_cache"].sudo()
        now = fields.Datetime.now()
        recs = Cache.search(
            [
                ("index_id", "in", [int(i) for i in index_ids]),
                ("json_cache_until", ">=", now),
            ]
        )
        out: Dict[int, Dict[str, Any]] = {}
        for rec in recs:
            body = (rec.json_cache or {}).get("body") if rec.json_cache else None
            if not body:
                continue
            if body.get("body_html") is None:
                continue
            out[int(rec.index_id.id)] = {
                "body_html": body.get("body_html"),
                "body_text": body.get("body_text"),
                "attachments": body.get("attachments", []),
            }
        return out

    # DTO builder (mirror OpenMessage)
    def build_open_message_dto_from_cache(
        self, *, index_rec: Any, cached: Dict[str, Any], account: Any, folder: Any
    ) -> Dict[str, Any]:
        return self._open_message._build_response_from_cache(
            index_rec, cached, account, folder
        )

    def hydrate_message(self, index_rec: Any, folder: Any) -> Dict[str, Any]:
        """
        Fetch message body from provider via OpenMessage use case.

        Uses savepoint to isolate from concurrent hydration failures.
        """
        params = OpenMessageParams(
            uid=str(index_rec.uid),
            index_id=int(index_rec.id),
            folder_id=int(folder.id) if folder else None,
            account_id=int(index_rec.account_id.id),
        )
        # Use savepoint to isolate this operation
        # If another concurrent request is hydrating the same message,
        # we may get SerializationFailure - rollback savepoint and raise
        try:
            self.env.cr.execute("SAVEPOINT hydrate_msg_%s", (int(index_rec.id),))
            result = self._open_message.execute(params)
            self.env.cr.execute(
                "RELEASE SAVEPOINT hydrate_msg_%s", (int(index_rec.id),)
            )
            return result
        except Exception:
            self.env.cr.execute(
                "ROLLBACK TO SAVEPOINT hydrate_msg_%s", (int(index_rec.id),)
            )
            raise
