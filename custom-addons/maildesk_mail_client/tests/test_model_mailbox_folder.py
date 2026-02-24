# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Model tests for `models/mailbox_folder.py`.

Focus: provider routing of folder sync (IMAP vs Outlook) without external network.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..models.mailbox_folder import MailboxFolder
from .common import context_manager_return


class TestMailboxFolderSync(TransactionCase):
    """Integration-style tests for mailbox.folder folder sync entrypoints."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()

    def _make_account(self, *, server_type: str, host: str, email: str):
        server = self.FetchmailServer.create(
            {
                "name": "Mail Server",
                "server_type": server_type,
                "server": host,
                "port": 993,
                "user": email,
                "password": "secret",
                "is_ssl": True,
            }
        )
        return self.Account.create(
            {
                "name": email,
                "email": email,
                "owner_id": self.env.user.id,
                "access_user_ids": [(6, 0, [self.env.user.id])],
                "mail_server_id": server.id,
            }
        )

    def test_sync_folders_for_account_imap_path_calls_ensure_inbox_and_sync_all(self):
        """IMAP path uses authenticated IMAP client and triggers inbox + folder sync helpers."""

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            account = self._make_account(
                server_type="imap", host="imap.example.com", email="imap@example.com"
            )

        called = {"ensure": 0, "sync_all": 0, "bootstrap": 0}

        class DummyClient:
            def logout(self):
                return None

        with (
            patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_folder.build_authenticated_imap_client",
                autospec=True,
                side_effect=lambda env, acc: context_manager_return(DummyClient()),
            ),
            patch.object(
                MailboxFolder,
                "_ensure_inbox",
                autospec=True,
                side_effect=lambda _self, _cli, _acc: called.__setitem__(
                    "ensure", called["ensure"] + 1
                ),
            ),
            patch.object(
                MailboxFolder,
                "_sync_all",
                autospec=True,
                side_effect=lambda _self, _cli, _acc: called.__setitem__(
                    "sync_all", called["sync_all"] + 1
                ),
            ),
            patch.object(
                MailboxFolder,
                "bootstrap_if_pending",
                autospec=True,
                side_effect=lambda _self: called.__setitem__(
                    "bootstrap", called["bootstrap"] + 1
                ),
            ),
        ):
            self.env["mailbox.folder"].sync_folders_for_account(account)

        self.assertEqual(called["ensure"], 1)
        self.assertEqual(called["sync_all"], 1)
        self.assertEqual(called["bootstrap"], 0)

    def test_sync_folders_for_account_outlook_path_routes_to_graph(self):
        """Outlook server_type routes to Graph sync helper and does not touch IMAP."""

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            account = self._make_account(
                server_type="outlook",
                host="outlook.office365.com",
                email="outlook@example.com",
            )

        with (
            patch.object(
                MailboxFolder,
                "_sync_outlook_graph",
                autospec=True,
                return_value={"ok": True},
            ) as sync_graph,
            patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_folder.build_authenticated_imap_client",
                side_effect=AssertionError("must not use IMAP for outlook server_type"),
            ),
        ):
            self.env["mailbox.folder"].sync_folders_for_account(account)

        sync_graph.assert_called_once()

    def test_sync_folders_for_account_can_trigger_bootstrap_via_context(self):
        """Folder sync may optionally trigger bootstrap when requested via context."""

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            account = self._make_account(
                server_type="imap", host="imap.example.com", email="imap@example.com"
            )

        called = {"ensure": 0, "sync_all": 0, "bootstrap": 0}

        class DummyClient:
            def logout(self):
                return None

        with (
            patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_folder.build_authenticated_imap_client",
                autospec=True,
                side_effect=lambda env, acc: context_manager_return(DummyClient()),
            ),
            patch.object(
                MailboxFolder,
                "_ensure_inbox",
                autospec=True,
                side_effect=lambda _self, _cli, _acc: called.__setitem__(
                    "ensure", called["ensure"] + 1
                ),
            ),
            patch.object(
                MailboxFolder,
                "_sync_all",
                autospec=True,
                side_effect=lambda _self, _cli, _acc: called.__setitem__(
                    "sync_all", called["sync_all"] + 1
                ),
            ),
            patch.object(
                MailboxFolder,
                "bootstrap_if_pending",
                autospec=True,
                side_effect=lambda _self: called.__setitem__(
                    "bootstrap", called["bootstrap"] + 1
                ),
            ),
        ):
            self.env["mailbox.folder"].with_context(
                maildesk_bootstrap_after_folder_sync=True
            ).sync_folders_for_account(account)

        self.assertEqual(called["ensure"], 1)
        self.assertEqual(called["sync_all"], 1)
        self.assertEqual(called["bootstrap"], 1)
