# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/sync_outlook_delta.py`.

Focus: deterministic delta orchestration (lease/backoff, delta-expired recovery).
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase

from ..application.use_cases.sync_outlook_delta import (
    DeltaExpiredError,
    SyncOutlookDelta,
)
from .common import FakeNotifier


class TestSyncOutlookDelta(TransactionCase):
    """Validate Outlook delta sync orchestration invariants."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()

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
                    "outlook_delta_tokens": {"message_delta_by_folder": {}},
                    "backoff_until": fields.Datetime.now(),
                }
            )

    def test_delta_expired_resets_folder_state_and_tokens(self):
        """Delta expiration forces a full refresh by resetting cursors and folder state."""

        account = self._make_outlook_account()
        folder = self.Folder.create(
            {
                "name": "Inbox",
                "imap_name": "Inbox",
                "account_id": account.id,
                "sync_state": "incremental",
                "last_uid": 123,
                "backfill_last_uid": 123,
                "backfill_fetched_count": 10,
                "backfill_total_estimate": 100,
            }
        )

        notifier = FakeNotifier()
        use_case = SyncOutlookDelta(self.env, notifier=notifier, lease_ttl_seconds=60)

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.sync_outlook_delta.get_outlook_client",
                return_value=(object(), "https://graph.example"),
            ),
            patch.object(use_case, "_build_folder_map", return_value={"FID": "Inbox"}),
            patch.object(use_case, "_incremental", side_effect=DeltaExpiredError()),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.try_acquire",
                return_value=True,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.release",
                return_value=True,
            ),
        ):
            res = use_case.execute(account.id)

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("mode"), "delta_expired")

        account.invalidate_recordset()
        self.assertFalse(account.outlook_delta_tokens)
        self.assertFalse(bool(account.outlook_delta_link))
        self.assertFalse(bool(account.backoff_until))

        folder.invalidate_recordset()
        self.assertEqual(folder.sync_state, "backfill_pending")
        self.assertEqual(folder.last_uid, 0)
        self.assertEqual(folder.backfill_last_uid, 0)
        self.assertEqual(folder.backfill_fetched_count, 0)
        self.assertEqual(folder.backfill_total_estimate, 0)

        self.assertIn("notify_full_refresh", [c.name for c in notifier.calls])

    def test_successful_sync_clears_backoff(self):
        """Successful delta sync clears backoff_until even if it was set."""

        account = self._make_outlook_account()
        notifier = FakeNotifier()
        use_case = SyncOutlookDelta(self.env, notifier=notifier, lease_ttl_seconds=60)

        def _fake_incremental(_account, _sess, _base, _owner, _folder_map):
            _account.write(
                {
                    "outlook_delta_tokens": {
                        "message_delta_by_folder": {"FID": {"cursor": "c"}}
                    }
                }
            )
            return {
                "ok": True,
                "changes": False,
                "deleted": 0,
                "truncated": False,
                "new_count": 0,
            }

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.sync_outlook_delta.get_outlook_client",
                return_value=(object(), "https://graph.example"),
            ),
            patch.object(use_case, "_build_folder_map", return_value={"FID": "Inbox"}),
            patch.object(use_case, "_incremental", side_effect=_fake_incremental),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.try_acquire",
                return_value=True,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.release",
                return_value=True,
            ),
        ):
            res = use_case.execute(account.id)

        self.assertTrue(res.get("ok"))
        account.invalidate_recordset()
        self.assertFalse(bool(account.backoff_until))
        self.assertIn("message_delta_by_folder", account.outlook_delta_tokens or {})
