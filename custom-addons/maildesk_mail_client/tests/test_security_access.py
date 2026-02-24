# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger
from odoo.exceptions import AccessError


@tagged("security", "post_install", "-at_install")
class TestMailboxSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Create Users
        with mute_logger("odoo.addons.base.models.ir_mail_server"):
            cls.user_allowed = cls.env["res.users"].create(
                {
                    "name": "Allowed User",
                    "login": "user_allowed",
                    "email": "allowed@test.com",
                    "group_ids": [
                        (
                            6,
                            0,
                            [cls.env.ref("maildesk_mail_client.group_mailbox_user").id],
                        )
                    ],
                }
            )

            cls.user_denied = cls.env["res.users"].create(
                {
                    "name": "Denied User",
                    "login": "user_denied",
                    "email": "denied@test.com",
                    "group_ids": [
                        (
                            6,
                            0,
                            [cls.env.ref("maildesk_mail_client.group_mailbox_user").id],
                        )
                    ],
                }
            )

        # Create Mailbox Account
        cls.account = cls.env["mailbox.account"].create(
            {
                "name": "Secure Account",
                "email": "secure@test.com",
                "access_user_ids": [(4, cls.user_allowed.id)],
            }
        )

        # Create Folder
        cls.folder = cls.env["mailbox.folder"].create(
            {"name": "Inbox", "account_id": cls.account.id, "folder_type": "inbox"}
        )

        # Create Message
        cls.message = cls.env["maildesk.message_index"].create(
            {
                "account_id": cls.account.id,
                "folder": "Inbox",
                "uid": "123",
                "subject": "Secret Message",
                "provider": "imap",
            }
        )

    def test_account_visibility(self):
        """Verify account visibility based on access_user_ids"""
        # Allowed user should see the account
        allowed_accounts = (
            self.env["mailbox.account"]
            .with_user(self.user_allowed)
            .search([("id", "=", self.account.id)])
        )
        self.assertEqual(
            len(allowed_accounts), 1, "Allowed user should see the account"
        )

        # Denied user should NOT see the account
        denied_accounts = (
            self.env["mailbox.account"]
            .with_user(self.user_denied)
            .search([("id", "=", self.account.id)])
        )
        self.assertEqual(
            len(denied_accounts), 0, "Denied user should NOT see the account"
        )

    def test_folder_visibility(self):
        """Verify folder visibility cascades from account"""
        # Allowed user should see the folder
        allowed_folders = (
            self.env["mailbox.folder"]
            .with_user(self.user_allowed)
            .search([("id", "=", self.folder.id)])
        )
        self.assertEqual(len(allowed_folders), 1, "Allowed user should see the folder")

        # Denied user should NOT see the folder
        denied_folders = (
            self.env["mailbox.folder"]
            .with_user(self.user_denied)
            .search([("id", "=", self.folder.id)])
        )
        self.assertEqual(
            len(denied_folders), 0, "Denied user should NOT see the folder"
        )

    def test_message_visibility(self):
        """Verify message visibility cascades from account"""
        # Allowed user should see the message
        allowed_msgs = (
            self.env["maildesk.message_index"]
            .with_user(self.user_allowed)
            .search([("id", "=", self.message.id)])
        )
        self.assertEqual(len(allowed_msgs), 1, "Allowed user should see the message")

        # Denied user should NOT see the message
        denied_msgs = (
            self.env["maildesk.message_index"]
            .with_user(self.user_denied)
            .search([("id", "=", self.message.id)])
        )
        self.assertEqual(len(denied_msgs), 0, "Denied user should NOT see the message")

    @mute_logger("odoo.addons.base.models.ir_model")
    def test_direct_read_access_blocked(self):
        """Verify direct read() is blocked for denied user"""
        with self.assertRaises(AccessError):
            self.account.with_user(self.user_denied).read(["name"])

    @mute_logger("odoo.addons.base.models.ir_model")
    def test_write_access_blocked(self):
        """Verify write() is blocked for denied user"""
        with self.assertRaises(AccessError):
            self.account.with_user(self.user_denied).write({"name": "Hacked"})
