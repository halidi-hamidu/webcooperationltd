# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..infrastructure.adapters.ingest_queue_adapter import IngestQueueAdapter


class TestIngestAllowedGate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()

    def _make_imap_account(self):
        server = self.FetchmailServer.create(
            {
                "name": "IMAP Server",
                "server_type": "imap",
                "server": "imap.example.com",
                "port": 993,
                "user": "imap@example.com",
                "password": "secret",
                "is_ssl": True,
            }
        )
        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            return self.Account.create(
                {
                    "name": "IMAP Account",
                    "email": "imap@example.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                }
            )

    def test_scan_candidate_index_ids_requires_ingest_allowed(self):
        account = self._make_imap_account()
        now = datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)

        rec = self.Index.create(
            {
                "account_id": account.id,
                "provider": "imap",
                "folder": "INBOX",
                "uid": "1",
                "date": now,
                "message_id": "openerp-123",  # matches adapter's fallback pattern
            }
        )

        adapter = IngestQueueAdapter(self.env)
        ids = adapter.scan_candidate_index_ids(batch=500)
        self.assertNotIn(rec.id, ids)

        rec.write({"ingest_allowed": True})
        ids = adapter.scan_candidate_index_ids(batch=500)
        self.assertIn(rec.id, ids)
