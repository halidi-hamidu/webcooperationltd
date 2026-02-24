# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for IMAP folder discovery cursor semantics.

Folder discovery (LIST/STATUS) must never reset sync cursors such as `last_uid`.
Those cursors are only allowed to move forward after successful SSOT upserts in
bootstrap/incremental sync flows.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase

from .common import context_manager_return


class TestFolderDiscoveryDoesNotResetCursor(TransactionCase):
    """Validate that folder discovery never resets `last_uid`."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()

    def test_existing_folder_last_uid_is_preserved_on_sync_all(self):
        """
        Regression guard:
        Syncing the folder tree must not overwrite `last_uid` for existing folders,
        otherwise incremental sync can permanently skip messages ("missing mails").
        """
        server = self.FetchmailServer.create(
            {
                "name": "IMAP Server",
                "server_type": "imap",
                "server": "imap.example.com",
                "port": 993,
                "user": "imap@example.com",
                "password": "secret",
                "is_ssl": True,
            }
        )
        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            account = self.Account.create(
                {
                    "name": "IMAP Account",
                    "email": "imap@example.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                }
            )

        # Existing folder already partially synced.
        f = self.Folder.create(
            {
                "name": "Unter Inbox",
                "imap_name": "Unter Inbox",
                "account_id": account.id,
                "sync_state": "incremental",
                "last_uid": 123,
                "uid_validity": 1,
            }
        )

        class DummyClient:
            def list_folders(self):
                return [([], b"/", b"Unter Inbox")]

            def folder_status(self, _name, _items):
                return {b"UIDVALIDITY": 1, b"UIDNEXT": 200, b"UNSEEN": 0}

            def logout(self):
                return None

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_folder.build_authenticated_imap_client",
            autospec=True,
            side_effect=lambda env, acc: context_manager_return(DummyClient()),
        ):
            self.env["mailbox.folder"].sync_folders_for_account(account)

        f.invalidate_recordset()
        self.assertEqual(f.last_uid, 123)
