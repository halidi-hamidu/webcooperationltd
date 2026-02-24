# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

from unittest.mock import patch
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from imapclient.imap_utf7 import encode as imap_utf7_encode


@tagged("post_install", "-at_install")
class TestFolderUtf7Decode(TransactionCase):
    def setUp(self):
        super().setUp()

        self.fetch_srv = self.env["fetchmail.server"].create(
            {
                "name": "UTF-7 IMAP",
                "server": "imap.example.com",
                "port": 993,
                "is_ssl": True,
                "server_type": "imap",
                "user": "user",
                "password": "pwd",
            }
        )
        self.account = self.env["mailbox.account"].create(
            {
                "name": "UTF-7 Account",
                "email": "user@example.com",
                "mail_server_id": self.fetch_srv.id,
            }
        )

    def _dummy_client(self):
        """A minimal IMAPClient stub that returns one UTF-7 folder."""

        class Dummy:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def list_folders(self):
                return [
                    ((), "/", b"INBOX"),
                    ((), "/", imap_utf7_encode("Campañas")),
                    ((), "/", b"Campa&AMMAsQ-as"),  # «Campañas»
                ]

            def folder_status(self, *_a, **_kw):
                # UIDVALIDITY 1, UIDNEXT 1, UNSEEN 0
                return {b"UIDVALIDITY": b"1", b"UIDNEXT": b"1", b"UNSEEN": b"0"}

        return Dummy()

    # can be tested as
    # docker compose exec odoo_web  odoo -d prod -u $MODULE --stop-after-init --xmlrpc-port=8070 --db_host=db --db_user=odoo19 --db_password=odoo --test-enable  --test-tags .test_utf7_folder_is_decoded
    def test_utf7_folder_is_decoded(self):
        # patch the low-level connector used by `sync_folders_for_account`
        # and mock bootstrap_if_pending to avoid triggering real network calls in bootstrap phase
        with (
            patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_folder.build_authenticated_imap_client",
                return_value=self._dummy_client(),
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_folder.MailboxFolder.bootstrap_if_pending"
            ),
        ):
            self.env["mailbox.folder"].sync_folders_for_account(self.account)

        folder = self.env["mailbox.folder"].search(
            [
                ("account_id", "=", self.account.id),
                ("imap_name", "=", "Campañas"),  # decoded value
            ],
            limit=1,
        )
        self.assertTrue(folder, "UTF-8 Folder record should be created")
        raw_utf7 = imap_utf7_encode("Campañas").decode("ascii")
        self.assertFalse(
            self.env["mailbox.folder"].search(
                [("account_id", "=", self.account.id), ("imap_name", "=", raw_utf7)],
                limit=1,
            ),
            "Folder name must not be stored as raw modified UTF-7",
        )
        self.assertEqual(
            folder.name, "Campañas"
        )  # UTF-7 folder should be stored as "Campañas"
        self.assertEqual(folder.unread_count, 0)
