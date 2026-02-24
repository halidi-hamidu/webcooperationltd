# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
FetchThread Adapter: Implements FetchThreadDeps protocol for the FetchThread use-case.
"""

from ..providers.gmail.auth import gmail_build_service
from ..providers.gmail.thread_provider import gmail_get_thread_full
from ..providers.imap import get_pool


class FetchThreadAdapter:
    def __init__(self, env):
        self.env = env
        self._sync = env["mailbox.sync"]

    def cache_search(self, domain, limit):
        Index = self.env["maildesk.message_index"].sudo()
        return Index.search(domain, limit=limit)

    def cache_upsert_meta(self, account_id, folder, uid, vals, ttl_minutes):
        return False

    def folder_search(self, domain, limit):
        Folder = self.env["mailbox.folder"]
        return Folder.search(domain, limit=limit)

    def folder_imap_name(self, folder):
        return getattr(folder, "imap_name", None) if folder else None

    def folder_id(self, folder):
        return folder.id if folder else False

    def account_id(self, account):
        return account.id if account else 0

    def is_gmail_account(self, account):
        return account.is_gmail

    def gmail_build_service(self, account):
        return gmail_build_service(account)

    def gmail_get_thread_full(self, service, account, thread_id, include_bodies):
        return gmail_get_thread_full(
            self.env, None, service, account, thread_id, include_bodies
        )

    def get_pool(self, account):
        return get_pool(account)

    def is_outlook_account(self, account):
        return account.is_outlook if account else False

    def find_message_by_message_id(self, account, message_id):
        """
        Find a message in message_index by its Message-ID header.
        Returns a dict with uid, folder_id, in_reply_to for chain walking.
        """
        if not message_id:
            return None

        Index = self.env["maildesk.message_index"].sudo()

        # Normalize message_id (remove < > if present)
        normalized = message_id.strip()
        if normalized.startswith("<") and normalized.endswith(">"):
            normalized = normalized[1:-1]

        # Search by message_id (try both with and without brackets, case-insensitive)
        # Some providers store with <>, some without. Frontend might send normalized casing.
        msg = Index.search(
            [
                ("account_id", "=", account.id),
                "|",
                ("message_id", "=ilike", normalized),
                ("message_id", "=ilike", f"<{normalized}>"),
            ],
            limit=1,
        )

        if not msg:
            return None

        # Resolve folder_id from folder name / imap_name
        folder_rec = self.env["mailbox.folder"].search(
            [
                ("account_id", "=", account.id),
                "|",
                ("imap_name", "=", msg.folder),
                ("name", "=", msg.folder),
            ],
            limit=1,
        )

        return {
            "uid": msg.uid,
            "folder_id": folder_rec.id if folder_rec else False,
            "in_reply_to": msg.in_reply_to or "",
        }

    def get_thread_messages_from_db(self, account, thread_id, include_bodies=True):
        """
        Fetch thread messages from local database index.
        Used for Outlook accounts where we don't chase IMAP headers.
        """
        Index = self.env["maildesk.message_index"].sudo()
        messages = Index.search(
            [
                ("account_id", "=", account.id),
                ("thread_id", "=", thread_id),
            ],
            order="date asc",
        )

        if not messages:
            return []

        # Resolve folder IDs from imap_name/name
        folder_names = list(set(messages.mapped("folder")))
        folders = self.env["mailbox.folder"].search(
            [
                ("account_id", "=", account.id),
                "|",
                ("imap_name", "in", folder_names),
                ("name", "in", folder_names),
            ]
        )
        folder_map = {}
        for f in folders:
            if getattr(f, "imap_name", None):
                folder_map[f.imap_name] = f.id
            if getattr(f, "name", None):
                folder_map[f.name] = f.id

        result = []
        for msg in messages:
            folder_id = folder_map.get(msg.folder) or 0

            dto = {
                "id": msg.id,
                "uid": msg.uid,
                "msg_key": f"{account.id}|{folder_id}|{msg.uid}",
                "account_id": [account.id, account.name],
                "folder_id": folder_id,
                "message_id_norm": msg.message_id,
                "thread_id": msg.thread_id,
                "in_reply_to": msg.in_reply_to,
                "references_hdr": msg.references_hdr,
                "subject": msg.subject or "",
                "date": msg.date.isoformat() if msg.date else "",
                "sort_ts": int(msg.date.timestamp()) if msg.date else 0,
                "sender_display_name": msg.sender_display_name or msg.from_addr or "",
                "email_from": msg.from_addr or "",
                "is_read": msg.is_read,
                "is_starred": msg.is_starred,
                "preview_text": msg.preview or "",
            }
            result.append(dto)
        return result

    def get_message_with_attachments(self, params):
        return self._sync.get_message_with_attachments(params)

    def norm_msgid(self, msgid):
        return self._sync._norm_msgid(msgid)
