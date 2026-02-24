# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..infrastructure.providers.gmail.label_resolver import resolve_gmail_label


@tagged("post_install", "-at_install")
class TestGmailLabelResolverLocalized(TransactionCase):
    """Ensure localized IMAP folder names resolve to Gmail system labels."""

    def test_resolves_sent_label_from_folder_type_when_imap_name_is_localized(self):
        class FakeLabels:
            def list(self, userId):
                return self

            def execute(self):
                return {"labels": [{"id": "LBL_SENT", "name": "SENT"}]}

        class FakeUsers:
            def labels(self):
                return FakeLabels()

        class FakeService:
            def users(self):
                return FakeUsers()

        account = self.env["mailbox.account"].create(
            {
                "name": "Gmail Account",
                "email": "user@gmail.com",
            }
        )
        folder = self.env["mailbox.folder"].create(
            {
                "account_id": account.id,
                "name": "Enviados",
                "imap_name": "[Gmail]/Enviados",
                "folder_type": "sent",
            }
        )

        label_id, label_name = resolve_gmail_label(
            FakeService(), folder, folder_name=folder.imap_name
        )
        self.assertEqual(label_id, "LBL_SENT")
        self.assertEqual(label_name, "SENT")
