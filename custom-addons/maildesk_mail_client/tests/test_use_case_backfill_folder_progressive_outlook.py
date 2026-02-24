# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/backfill_folder_progressive_outlook.py`.

Focus: deterministic Outlook progressive backfill paging and SSOT/ingest effects.
Layer: tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.backfill_folder_progressive_outlook import (
    BackfillFolderProgressiveOutlook,
)
from ..domain.contracts import Message


class TestBackfillFolderProgressiveOutlook(TransactionCase):
    """Validate progressive backfill invariants for Outlook folders."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Config = cls.env["ir.config_parameter"].sudo()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()
        cls.Queue = cls.env["maildesk.ingest_queue"].sudo()

    def _make_outlook_account(self):
        server = self.FetchmailServer.create(
            {
                "name": "Outlook IMAP",
                "server_type": "imap",
                "server": "outlook.office365.com",
                "port": 993,
                "user": "outlook@example.com",
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
                    "name": "Outlook Account",
                    "email": "outlook@example.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                    "imap_caps": {"tokens": ["MICROSOFT"]},
                }
            )

    def test_backfill_marks_complete_when_next_link_missing(self):
        """Backfill upserts SSOT rows and sets completed_at on the last page."""

        self.Config.set_param("maildesk.backfill_batch_size", "100")
        self.Config.set_param("maildesk.backfill_job_budget_seconds", "25")
        self.Config.set_param("maildesk.backfill_max_total_per_folder", "20000")

        account = self._make_outlook_account()
        folder = self.Folder.create(
            {
                "name": "Inbox",
                "imap_name": "Inbox",
                "account_id": account.id,
                "sync_state": "incremental",
                "backfill_fetched_count": 0,
                "backfill_completed_at": False,
            }
        )

        now = datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
        msgs = [
            Message(
                id="o1",
                thread_id="c1",
                account_id=account.id,
                message_header_id="<o1@example.com>",
                in_reply_to="",
                references="",
                date=now,
                subject="One",
                email_from="sender@example.com",
                sender_display_name="Sender",
                to_display="outlook@example.com",
                cc_display="",
                bcc_display="",
                snippet="",
                is_read=False,
                is_starred=False,
                has_attachments=False,
                metadata={},
            ),
            Message(
                id="o2",
                thread_id="c1",
                account_id=account.id,
                message_header_id="<o2@example.com>",
                in_reply_to="",
                references="",
                date=now,
                subject="Two",
                email_from="sender@example.com",
                sender_display_name="Sender",
                to_display="outlook@example.com",
                cc_display="",
                bcc_display="",
                snippet="",
                is_read=True,
                is_starred=True,
                has_attachments=False,
                metadata={},
            ),
        ]

        use_case = BackfillFolderProgressiveOutlook(self.env)

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.backfill_folder_progressive_outlook.get_outlook_client",
                return_value=(object(), "https://graph.example"),
            ),
            patch.object(use_case, "_resolve_folder_graph_id", return_value="FID"),
            patch.object(use_case, "_folder_total", return_value=2),
            patch.object(
                use_case, "_list_message_ids", return_value=(["o1", "o2"], None)
            ),
            patch.object(use_case, "_fetch_messages", return_value=msgs),
        ):
            res = use_case.execute(folder.id)

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("fetched"), 2)
        self.assertTrue(res.get("complete"))

        folder.invalidate_recordset()
        self.assertEqual(folder.backfill_fetched_count, 2)
        self.assertEqual(folder.backfill_total_estimate, 2)
        self.assertTrue(bool(folder.backfill_completed_at))
        self.assertEqual(folder.outlook_graph_id, "FID")
        self.assertEqual(folder.outlook_backfill_next_link, "")

        count = self.Index.search_count(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "outlook"),
                ("folder", "=", "Inbox"),
            ]
        )
        self.assertEqual(count, 2)
