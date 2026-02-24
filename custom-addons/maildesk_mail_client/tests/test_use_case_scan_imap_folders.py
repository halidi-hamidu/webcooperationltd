# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/scan_imap_folders.py`.

Focus: Phase-1 scan marks folders dirty based on STATUS changes (UIDNEXT/MODSEQ).
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.scan_imap_folders import ScanImapFolders
from .common import context_manager_return


class TestScanImapFolders(TransactionCase):
    """Validate scan-only change detection."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()

    def test_scan_marks_folder_needs_sync_on_uidnext_change(self):
        """If UIDNEXT increases, the folder is marked needs_sync=True."""

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
        folder = self.Folder.create(
            {
                "name": "INBOX",
                "imap_name": "INBOX",
                "account_id": account.id,
                "sync_state": "incremental",
                "uid_validity": 1,
                "last_uidnext": 2,
                "last_highest_modseq": "0",
                "unread_count": 0,
                "needs_sync": False,
            }
        )

        class DummyClient:
            def has_capability(self, cap: str) -> bool:
                return cap == "CONDSTORE"

            def status(self, folder_name, fields):
                return {
                    folder_name: {
                        b"UIDNEXT": 5,
                        b"UIDVALIDITY": 1,
                        b"UNSEEN": 3,
                        b"HIGHESTMODSEQ": 20,
                    }
                }

        def _safe(_op, _folder_name, fn):
            return fn()

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.scan_imap_folders.build_authenticated_imap_client",
                autospec=True,
                side_effect=lambda env, acc: context_manager_return(DummyClient()),
            ),
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.scan_imap_folders.safe_folder_operation",
                side_effect=_safe,
            ),
        ):
            ScanImapFolders(self.env).execute(account)

        folder.invalidate_recordset()
        self.assertTrue(folder.needs_sync)
        self.assertEqual(folder.unread_count, 3)
        self.assertTrue(bool(folder.unread_count_updated_at))
