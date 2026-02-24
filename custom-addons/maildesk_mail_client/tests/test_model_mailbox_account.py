# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Model tests for `models/mailbox_account.py`.

Focus: UI polling entrypoint must be non-blocking and only enqueue async work.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo import api
from odoo.tests.common import TransactionCase


class TestMailboxAccountPolling(TransactionCase):
    """Integration-style tests for mailbox.account polling entrypoints."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()

    def _make_account(self, email: str):
        # poll_mail_accounts enqueues via a separate cursor/transaction, so this
        # helper creates accounts in a committed transaction to make them
        # visible across cursors.
        with self.env.registry.cursor() as cr:
            env2 = api.Environment(cr, self.env.uid, {})
            server = (
                env2["fetchmail.server"]
                .sudo()
                .create(
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
            )
            with patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
                return_value=None,
            ):
                acc = (
                    env2["mailbox.account"]
                    .sudo()
                    .create(
                        {
                            "name": email,
                            "email": email,
                            "owner_id": env2.user.id,
                            "access_user_ids": [(6, 0, [env2.user.id])],
                            "mail_server_id": server.id,
                        }
                    )
                )
                acc_id = acc.id

        return self.env["mailbox.account"].browse(acc_id)

    def test_poll_mail_accounts_enqueues_requests_and_is_idempotent(self):
        """
        UI polling must not run provider sync; it only enqueues async work.

        Repeated polls must not create duplicate requests per account.
        """

        a1 = self._make_account("a1@example.com")
        a2 = self._make_account("a2@example.com")
        test_accounts = self.Account.browse([a1.id, a2.id])

        with (
            patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.search",
                autospec=True,
                return_value=test_accounts,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount._poll_single_account",
                autospec=True,
                side_effect=AssertionError(
                    "_poll_single_account must not be called by UI polling"
                ),
            ),
        ):
            res1 = self.env["mailbox.account"].poll_mail_accounts()
            res2 = self.env["mailbox.account"].poll_mail_accounts()

        self.assertFalse(res1["changes"])
        self.assertEqual(res1["requested_accounts"], 2)
        self.assertEqual(res1["queued_accounts"], 2)

        self.assertFalse(res2["changes"])
        self.assertEqual(res2["requested_accounts"], 2)
        self.assertEqual(res2["queued_accounts"], 0)
