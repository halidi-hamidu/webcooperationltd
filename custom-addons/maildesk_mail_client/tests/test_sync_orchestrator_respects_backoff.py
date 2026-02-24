# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for sync orchestrator backoff filtering (demo safety)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase


class TestSyncOrchestratorRespectsBackoff(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()

    def _make_imap_server(self, name="IMAP Server"):
        return self.FetchmailServer.create(
            {
                "name": name,
                "server_type": "imap",
                "server": "example.invalid",
                "port": 993,
                "user": "u",
                "password": "p",
                "is_ssl": True,
                "state": "done",
            }
        )

    def test_sync_all_skips_accounts_in_backoff(self):
        due_server = self._make_imap_server(name="IMAP Due")
        blocked_server = self._make_imap_server(name="IMAP Blocked")

        due = self.Account.create(
            {
                "name": "Due",
                "email": "due@example.com",
                "mail_server_id": due_server.id,
                "backoff_until": False,
            }
        )
        blocked = self.Account.create(
            {
                "name": "Blocked",
                "email": "blocked@example.com",
                "mail_server_id": blocked_server.id,
                "backoff_until": fields.Datetime.to_string(
                    fields.Datetime.now() + timedelta(days=3650)
                ),
            }
        )

        Sync = self.env["maildesk.sync_orchestrator"]
        called = []

        def _spy(self, account_id):  # noqa: ARG001
            called.append(int(account_id))

        with patch.object(type(Sync), "sync_account", _spy):
            Sync.sync_all()

        self.assertIn(due.id, called)
        self.assertNotIn(blocked.id, called)

    def test_sync_account_skips_non_imap_and_missing_host(self):
        Sync = self.env["maildesk.sync_orchestrator"]

        # Missing host
        bad_server = self.FetchmailServer.create(
            {
                "name": "IMAP Missing Host",
                "server_type": "imap",
                "server": False,
                "port": 993,
                "user": "u",
                "password": "p",
                "is_ssl": True,
                "state": "done",
            }
        )
        bad = self.Account.create(
            {
                "name": "Bad",
                "email": "bad@example.com",
                "mail_server_id": bad_server.id,
                "backoff_until": False,
            }
        )

        # Non-IMAP provider should never fall back to IMAP (use Outlook marker).
        outlook_server = self.FetchmailServer.create(
            {
                "name": "Outlook Server",
                "server_type": "outlook",
                "server": "outlook.office365.com",
                "port": 993,
                "user": "outlook@example.com",
                "password": "p",
                "is_ssl": True,
                "state": "done",
            }
        )
        outlook = self.Account.create(
            {
                "name": "Outlook",
                "email": "outlook@example.com",
                "mail_server_id": outlook_server.id,
                "backoff_until": False,
            }
        )

        with patch.object(
            type(Sync),
            "_dispatch_imap",
            side_effect=AssertionError("must not dispatch imap"),
        ):
            Sync.sync_account(bad.id)
            Sync.sync_account(outlook.id)
