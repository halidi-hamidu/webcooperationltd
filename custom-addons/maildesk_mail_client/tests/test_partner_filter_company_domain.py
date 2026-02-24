# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Regression tests for company-domain partner filtering in MailDesk."""

from __future__ import annotations

from odoo.tests.common import TransactionCase


class TestPartnerFilterCompanyDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()
        cls.Partner = cls.env["res.partner"].sudo()
        cls.Sync = cls.env["mailbox.sync"].sudo()

    def test_company_partner_filters_by_domain(self):
        user = self.env.user
        acc = self.Account.create(
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
        msg = self.Index.create(
            {
                "account_id": acc.id,
                "provider": "imap",
                "folder": "INBOX",
                "uid": "401",
                "from_addr": "ceo@acme.example",
                "to_addrs": "",
                "cc_addrs": "",
                "bcc_addrs": "",
                "deleted_on_server": False,
                "pending_delete": False,
            }
        )

        res = self.Sync.message_search_load(
            account_id=acc.id,
            folder_id=None,
            partner_id=company.id,
            offset=0,
            limit=30,
        )
        ids = [r.get("id") for r in (res.get("records") or [])]
        self.assertIn(msg.id, ids)
