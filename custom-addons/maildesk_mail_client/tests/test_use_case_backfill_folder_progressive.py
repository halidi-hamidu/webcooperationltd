# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/backfill_folder_progressive.py`.

Focus: cursor advancement and completion semantics for IMAP progressive backfill.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.backfill_folder_progressive import (
    BackfillFolderProgressive,
)
from .common import context_manager_return


class TestBackfillFolderProgressiveImap(TransactionCase):
    """Validate progressive backfill invariants for IMAP folders."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Config = cls.env["ir.config_parameter"].sudo()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Queue = cls.env["maildesk.ingest_queue"].sudo()
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
        return self.Account.create(
            {
                "name": "IMAP Account",
                "email": "imap@example.com",
                "owner_id": self.env.user.id,
                "access_user_ids": [(6, 0, [self.env.user.id])],
                "mail_server_id": server.id,
            }
        )

    def test_backfill_advances_cursor_to_min_fetched_minus_one(self):
        """Backfill cursor advances to min(fetched_uids)-1, not to the batch start."""

        self.Config.set_param("maildesk.backfill_batch_size", "10")
        self.Config.set_param("maildesk.backfill_job_budget_seconds", "25")
        self.Config.set_param("maildesk.backfill_max_total_per_folder", "20000")

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            account = self._make_imap_account()
        folder = self.Folder.create(
            {
                "name": "INBOX",
                "imap_name": "INBOX",
                "account_id": account.id,
                "sync_state": "incremental",
                "backfill_last_uid": 10,
                "backfill_fetched_count": 0,
            }
        )

        class DummyClient:
            def select_folder(self, _name, readonly=True):
                return None

        use_case = BackfillFolderProgressive(self.env)

        first_batch = [{"uid": 8}, {"uid": 9}, {"uid": 10}]

        before_queue = self.Queue.search_count([])
        before_index = self.Index.search_count(
            [("account_id", "=", account.id), ("provider", "=", "imap")]
        )

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.backfill_folder_progressive.build_authenticated_imap_client",
                autospec=True,
                side_effect=lambda env, acc: context_manager_return(DummyClient()),
            ),
            patch.object(
                use_case,
                "_fetch_imap_messages",
                side_effect=[first_batch, []],
            ),
        ):
            res = use_case.execute(folder.id)

        after_queue = self.Queue.search_count([])
        after_index = self.Index.search_count(
            [("account_id", "=", account.id), ("provider", "=", "imap")]
        )

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("fetched"), 3)

        folder.invalidate_recordset()
        self.assertEqual(folder.backfill_last_uid, 7)
        self.assertEqual(folder.backfill_fetched_count, 3)
        self.assertFalse(bool(folder.backfill_completed_at))

        self.assertEqual(after_queue - before_queue, 0)
        self.assertEqual(after_index - before_index, 3)

    def test_backfill_marks_complete_when_cursor_reaches_one(self):
        """When backfill_last_uid <= 1, the slice completes without fetching."""

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            account = self._make_imap_account()
        folder = self.Folder.create(
            {
                "name": "INBOX",
                "imap_name": "INBOX",
                "account_id": account.id,
                "sync_state": "incremental",
                "backfill_last_uid": 1,
                "backfill_fetched_count": 0,
            }
        )

        res = BackfillFolderProgressive(self.env).execute(folder.id)

        self.assertTrue(res.get("ok"))
        self.assertTrue(res.get("complete"))
        self.assertEqual(res.get("fetched"), 0)

        folder.invalidate_recordset()
        self.assertTrue(bool(folder.backfill_completed_at))
