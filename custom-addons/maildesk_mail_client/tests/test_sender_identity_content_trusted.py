# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..application.services.sender_identity import SenderIdentityService


@tagged("post_install", "-at_install")
class TestSenderIdentityContentTrusted(TransactionCase):
    """Ensure HTML trust decisions do not depend on Sent-folder visual contact."""

    def test_sent_folder_sets_content_trusted_even_if_recipient_untrusted(self):
        class Deps:
            def partner_search(self, email):
                return False

            def avatar_html(self, email, partner):
                return ""

            def folder_type(self, folder):
                return "sent"

        svc = SenderIdentityService(Deps())
        identity = svc.resolve_visual_identity(
            from_addr="me@company.test",
            to_addrs="alice@company.test",
            sender_display_name_header="Me",
            folder=object(),
            folder_name_heuristic="Sent",
        )

        self.assertFalse(identity["partner_trusted"])
        self.assertTrue(identity["content_trusted"])

    def test_inbox_folder_keeps_content_trusted_equal_to_partner_trust(self):
        class Partner:
            trusted_partner = True
            display_name = "Alice"
            id = 1
            trusted_by_user_id = False

        class Deps:
            def partner_search(self, email):
                return Partner() if email == "alice@company.test" else False

            def avatar_html(self, email, partner):
                return ""

            def folder_type(self, folder):
                return "inbox"

        svc = SenderIdentityService(Deps())
        identity = svc.resolve_visual_identity(
            from_addr="alice@company.test",
            to_addrs="me@company.test",
            sender_display_name_header="Alice",
            folder=object(),
            folder_name_heuristic="INBOX",
        )

        self.assertTrue(identity["partner_trusted"])
        self.assertTrue(identity["content_trusted"])
