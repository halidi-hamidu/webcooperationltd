# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/bootstrap_folder_gmail.py`.

Focus: Gmail bootstrap folder state transition and SSOT seed without network.
Layer: tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.bootstrap_folder_gmail import BootstrapFolderGmail
from ..domain.contracts import Message


class TestBootstrapFolderGmail(TransactionCase):
    """Validate Gmail bootstrap invariants."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Config = cls.env["ir.config_parameter"].sudo()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()
        cls.Queue = cls.env["maildesk.ingest_queue"].sudo()

    def _make_gmail_account(self):
        server = self.FetchmailServer.create(
            {
                "name": "Gmail IMAP",
                "server_type": "imap",
                "server": "imap.gmail.com",
                "port": 993,
                "user": "gmail@example.com",
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
                    "name": "Gmail Account",
                    "email": "gmail@example.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                    "imap_caps": {"tokens": ["X-GM-EXT-1"]},
                }
            )

    def test_bootstrap_transitions_pending_to_incremental_and_seeds_ssot(self):
        """Bootstrap inserts SSOT rows and transitions folder state to incremental."""

        self.Config.set_param("maildesk.backfill_bootstrap_max", "2")
        self.Config.set_param("maildesk.backfill_mode", "progressive")

        account = self._make_gmail_account()
        folder = self.Folder.create(
            {
                "name": "INBOX",
                "imap_name": "INBOX",
                "account_id": account.id,
                "sync_state": "backfill_pending",
            }
        )

        now = datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
        msgs = [
            Message(
                id="m1",
                thread_id="t1",
                account_id=account.id,
                message_header_id="<m1@example.com>",
                in_reply_to="",
                references="",
                date=now,
                subject="One",
                email_from="sender@example.com",
                sender_display_name="Sender",
                to_display="gmail@example.com",
                cc_display="",
                bcc_display="",
                snippet="",
                is_read=False,
                is_starred=False,
                has_attachments=False,
                metadata={"gmail_label_ids": ["INBOX"]},
            ),
            Message(
                id="m2",
                thread_id="t2",
                account_id=account.id,
                message_header_id="<m2@example.com>",
                in_reply_to="",
                references="",
                date=now,
                subject="Two",
                email_from="sender@example.com",
                sender_display_name="Sender",
                to_display="gmail@example.com",
                cc_display="",
                bcc_display="",
                snippet="",
                is_read=True,
                is_starred=True,
                has_attachments=False,
                metadata={"gmail_label_ids": ["INBOX"]},
            ),
        ]

        use_case = BootstrapFolderGmail(self.env)

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.bootstrap_folder_gmail.gmail_build_service",
                return_value=object(),
            ),
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.bootstrap_folder_gmail.resolve_gmail_label",
                return_value=("LBL", "INBOX"),
            ),
            patch.object(
                use_case, "_list_message_ids", return_value=(["m1", "m2"], "")
            ),
            patch.object(use_case, "_label_total", return_value=2),
            patch.object(use_case, "_fetch_messages", return_value=msgs),
        ):
            res = use_case.execute(folder.id)

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "bootstrap")
        self.assertEqual(res.get("fetched"), 2)

        folder.invalidate_recordset()
        self.assertEqual(folder.sync_state, "incremental")
        self.assertEqual(folder.backfill_fetched_count, 2)
        self.assertEqual(folder.backfill_total_estimate, 2)
        self.assertTrue(bool(folder.backfill_started_at))
        self.assertTrue(bool(folder.backfill_completed_at))
        self.assertEqual(folder.gmail_label_id, "LBL")

        count = self.Index.search_count(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "gmail"),
                ("folder", "=", "INBOX"),
            ]
        )
        self.assertEqual(count, 2)
