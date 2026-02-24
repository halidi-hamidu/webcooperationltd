# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Regression tests for SSOT message_index string sanitization.

Postgres refuses NUL (0x00) characters in text/varchar columns. Some inbound
emails can contain such bytes which may reach decoded strings and then break
the SSOT INSERT.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestMessageIndexSanitization(TransactionCase):
    def test_upsert_one_strips_nul_chars(self):
        """
        `maildesk.message_index.upsert_one()` must strip NUL chars from string fields.

        The write path uses raw SQL INSERT; without sanitization Postgres raises:
        "A string literal cannot contain NUL (0x00) characters."
        """
        FetchmailServer = self.env["fetchmail.server"].sudo()
        Account = self.env["mailbox.account"].sudo()
        Index = self.env["maildesk.message_index"].sudo()

        server = FetchmailServer.create(
            {
                "name": "IMAP Server",
                "server_type": "imap",
                "server": "imap.example.com",
                "port": 993,
                "user": "nul@example.com",
                "password": "secret",
                "is_ssl": True,
            }
        )

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            account = Account.create(
                {
                    "name": "nul@example.com",
                    "email": "nul@example.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                }
            )

        subject = "Hello\x00World"
        preview = "A\x00B\x00C"
        msg_id = "<id\x00@example.com>"

        idx_id = Index.upsert_one(
            {
                "account_id": account.id,
                "provider": "imap",
                "folder": "INBOX",
                "uid": "1",
                "subject": subject,
                "preview": preview,
                "message_id": msg_id,
                "from_addr": "from\x00@example.com",
                "to_addrs": "to@example.com",
            }
        )

        self.assertTrue(idx_id)
        idx = Index.browse(idx_id).exists()
        self.assertTrue(idx)
        self.assertNotIn("\x00", idx.subject or "")
        self.assertNotIn("\x00", idx.preview or "")
        self.assertNotIn("\x00", idx.message_id or "")
        self.assertNotIn("\x00", idx.from_addr or "")
