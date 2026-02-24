# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Model tests for `models/res_partner.py` maildesk_email_count.

Focus: Counter must only include messages from mailbox accounts where the
current user is present in `mailbox.account.access_user_ids`.
Layer: tests.
"""

from __future__ import annotations

from odoo.tests.common import TransactionCase


class TestResPartnerMaildeskEmailCount(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()
        cls.Partner = cls.env["res.partner"].sudo()

    def test_email_count_respects_account_access(self):
        user = self.env.user

        acc_allowed = self.Account.create(
            {
                "name": "Allowed",
                "email": "allowed@example.com",
                "owner_id": user.id,
                "access_user_ids": [(6, 0, [user.id])],
            }
        )
        acc_denied = self.Account.create(
            {
                "name": "Denied",
                "email": "denied@example.com",
                "owner_id": user.id,
                "access_user_ids": [(6, 0, [])],
            }
        )

        partner = self.Partner.create(
            {
                "name": "Alice",
                "email": "alice@example.com",
            }
        )

        # Two indexed emails mention Alice, but only one is in an allowed account.
        self.Index.create(
            {
                "account_id": acc_allowed.id,
                "provider": "imap",
                "folder": "INBOX",
                "uid": "101",
                "from_addr": "alice@example.com",
                "to_addrs": "",
                "cc_addrs": "",
                "bcc_addrs": "",
                "deleted_on_server": False,
            }
        )
        self.Index.create(
            {
                "account_id": acc_denied.id,
                "provider": "imap",
                "folder": "INBOX",
                "uid": "201",
                "from_addr": "alice@example.com",
                "to_addrs": "",
                "cc_addrs": "",
                "bcc_addrs": "",
                "deleted_on_server": False,
            }
        )

        # Compute is user-context sensitive; read without sudo to use self.env.user.
        self.assertEqual(partner.with_user(user).maildesk_email_count, 1)

    def test_email_count_assigns_for_new_record(self):
        """
        Onchange/`new()` records (NewId) must always get a computed value.
        This guards against 'Compute method failed to assign ... maildesk_email_count'.
        """
        p = self.env["res.partner"].new({"name": "Draft Partner"})
        self.assertEqual(p.maildesk_email_count, 0)

    def test_company_email_count_uses_domain(self):
        user = self.env.user
        acc_allowed = self.Account.create(
            {
                "name": "Allowed",
                "email": "allowed@example.com",
                "owner_id": user.id,
                "access_user_ids": [(6, 0, [user.id])],
            }
        )
        company = self.Partner.create(
            {
                "name": "ACME",
                "is_company": True,
                "email": "info@acme.example",
            }
        )
        # Message does not mention info@acme.example, only another address in the domain.
        self.Index.create(
            {
                "account_id": acc_allowed.id,
                "provider": "imap",
                "folder": "INBOX",
                "uid": "301",
                "from_addr": "ceo@acme.example",
                "to_addrs": "",
                "cc_addrs": "",
                "bcc_addrs": "",
                "deleted_on_server": False,
                "pending_delete": False,
            }
        )

        self.assertEqual(company.with_user(user).maildesk_email_count, 1)
