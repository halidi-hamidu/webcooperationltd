# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Mail list direction filters.

Contract (UI semantics):
- Folder selection is always respected (search within the selected folder).
- "Incoming"/"Outgoing" further refine results by direction.
- Tags and search refine results in addition to folder + direction.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestMailListDirectionFilters(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()
        cls.Tag = cls.env["mail.message.tag"].sudo()
        cls.Sync = cls.env["mailbox.sync"].sudo()

    def _make_account(self, email: str):
        server = self.FetchmailServer.create(
            {
                "name": "IMAP Server",
                "server_type": "imap",
                "server": "imap.example.com",
                "port": 993,
                "user": email,
                "password": "secret",
                "is_ssl": True,
            }
        )
        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            return self.Account.create(
                {
                    "name": email,
                    "email": email,
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                }
            )

    def _make_folder(
        self, *, account_id: int, name: str, imap_name: str, folder_type: str
    ):
        return self.Folder.create(
            {
                "name": name,
                "imap_name": imap_name,
                "folder_type": folder_type,
                "account_id": account_id,
                "sync_state": "incremental",
            }
        )

    def _make_index(
        self,
        *,
        account_id: int,
        folder: str,
        uid: str,
        subject: str,
        from_addr: str,
        to_addrs: str = "",
        tag_ids=None,
    ):
        vals = {
            "account_id": account_id,
            "provider": "imap",
            "folder": folder,
            "uid": uid,
            "subject": subject,
            "from_addr": from_addr,
            "to_addrs": to_addrs,
            # Make defaults explicit for stability.
            "deleted_on_server": False,
            "pending_delete": False,
            "pending_move_to": False,
        }
        if tag_ids:
            vals["tag_ids"] = [(6, 0, list(tag_ids))]
        return self.Index.create(vals)

    def test_folder_and_direction_filters_are_intersected(self):
        account = self._make_account("me@example.com")
        inbox = self._make_folder(
            account_id=account.id, name="INBOX", imap_name="INBOX", folder_type="inbox"
        )
        sent = self._make_folder(
            account_id=account.id, name="Sent", imap_name="Sent", folder_type="sent"
        )

        inbox_incoming = self._make_index(
            account_id=account.id,
            folder=inbox.imap_name,
            uid="1",
            subject="Inbox Incoming",
            from_addr="alice@example.com",
        )
        inbox_outgoing = self._make_index(
            account_id=account.id,
            folder=inbox.imap_name,
            uid="2",
            subject="Inbox Outgoing",
            from_addr=account.email,
            to_addrs="bob@example.com",
        )
        sent_incoming = self._make_index(
            account_id=account.id,
            folder=sent.imap_name,
            uid="3",
            subject="Sent Incoming",
            from_addr="bob@example.com",
        )
        sent_outgoing = self._make_index(
            account_id=account.id,
            folder=sent.imap_name,
            uid="4",
            subject="Sent Outgoing",
            from_addr=account.email,
            to_addrs="carol@example.com",
        )

        # INBOX + Incoming => only inbox_incoming
        res = self.Sync.message_search_load(
            account_id=account.id,
            folder_id=inbox.id,
            filter="incoming",
            offset=0,
            limit=30,
        )
        ids = [r.get("id") for r in (res.get("records") or [])]
        self.assertIn(inbox_incoming.id, ids)
        self.assertNotIn(inbox_outgoing.id, ids)
        self.assertNotIn(sent_incoming.id, ids)
        self.assertNotIn(sent_outgoing.id, ids)

        # INBOX + Outgoing => only inbox_outgoing
        res = self.Sync.message_search_load(
            account_id=account.id,
            folder_id=inbox.id,
            filter="outgoing",
            offset=0,
            limit=30,
        )
        ids = [r.get("id") for r in (res.get("records") or [])]
        self.assertIn(inbox_outgoing.id, ids)
        self.assertNotIn(inbox_incoming.id, ids)
        self.assertNotIn(sent_incoming.id, ids)
        self.assertNotIn(sent_outgoing.id, ids)

        # Sent + Outgoing => only sent_outgoing
        res = self.Sync.message_search_load(
            account_id=account.id,
            folder_id=sent.id,
            filter="outgoing",
            offset=0,
            limit=30,
        )
        ids = [r.get("id") for r in (res.get("records") or [])]
        self.assertIn(sent_outgoing.id, ids)
        self.assertNotIn(sent_incoming.id, ids)
        self.assertNotIn(inbox_incoming.id, ids)
        self.assertNotIn(inbox_outgoing.id, ids)

        # Account-level + Outgoing => show recipient identity (sent-style rendering)
        res = self.Sync.message_search_load(
            account_id=account.id,
            folder_id=None,
            filter="outgoing",
            offset=0,
            limit=30,
        )
        recs = res.get("records") or []
        rec_by_id = {r.get("id"): r for r in recs}
        self.assertIn(sent_outgoing.id, rec_by_id)
        self.assertIn(
            "carol@example.com",
            (rec_by_id[sent_outgoing.id].get("sender_display_name") or ""),
        )

    def test_tags_and_search_refine_folder_and_direction(self):
        account = self._make_account("me2@example.com")
        sent = self._make_folder(
            account_id=account.id, name="Sent", imap_name="Sent", folder_type="sent"
        )

        tag = self.Tag.create({"name": "X", "color": 1})

        wanted = self._make_index(
            account_id=account.id,
            folder=sent.imap_name,
            uid="1",
            subject="Hello Outgoing Tagged",
            from_addr=account.email,
            to_addrs="alice@example.com",
            tag_ids=[tag.id],
        )
        other_same_folder = self._make_index(
            account_id=account.id,
            folder=sent.imap_name,
            uid="2",
            subject="Hello Outgoing Untagged",
            from_addr=account.email,
            to_addrs="bob@example.com",
        )
        other_direction = self._make_index(
            account_id=account.id,
            folder=sent.imap_name,
            uid="3",
            subject="Hello Incoming Tagged",
            from_addr="someone@example.com",
            tag_ids=[tag.id],
        )

        res = self.Sync.message_search_load(
            account_id=account.id,
            folder_id=sent.id,
            filter="outgoing",
            search="Tagged",
            tag_ids=[tag.id],
            offset=0,
            limit=30,
        )
        ids = [r.get("id") for r in (res.get("records") or [])]
        self.assertIn(wanted.id, ids)
        self.assertNotIn(other_same_folder.id, ids)
        self.assertNotIn(other_direction.id, ids)
