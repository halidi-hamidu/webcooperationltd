# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for bypassing IMAP confirm-login for MailDesk Graph accounts."""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestFetchmailConfirmLoginGraphBypass(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()

    def _make_outlook_server(self):
        return self.FetchmailServer.create(
            {
                "name": "Outlook Server",
                "server_type": "outlook",
                "server": "outlook.office365.com",
                "port": 993,
                "user": "outlook@example.com",
                "password": "secret",
                "is_ssl": True,
                "state": "draft",
            }
        )

    def test_confirm_login_bypasses_imap_for_graph_account(self):
        server = self._make_outlook_server()
        self.Account.create(
            {
                "name": "Graph Account",
                "email": "graph@example.com",
                "mail_server_id": server.id,
                "outlook_graph_access_token": "AT",
            }
        )

        with patch.object(
            type(server),
            "_connect__",
            side_effect=AssertionError("IMAP must not be called"),
        ):
            ok = server.button_confirm_login()

        self.assertTrue(ok)
        server.invalidate_recordset()
        self.assertEqual(server.state, "done")

    def test_confirm_login_keeps_behavior_for_non_graph_outlook_server(self):
        server = self._make_outlook_server()

        class _DummyConn:
            def disconnect(self):
                return None

        with patch.object(
            type(server), "_connect__", return_value=_DummyConn()
        ) as mocked_connect:
            ok = server.button_confirm_login()

        self.assertTrue(ok)
        self.assertTrue(mocked_connect.called)
        server.invalidate_recordset()
        self.assertEqual(server.state, "done")
