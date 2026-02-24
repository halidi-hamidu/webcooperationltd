# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/sync_gmail_incremental.py` and `sync_gmail_history.py`.

Focus: orchestration invariants (lease handling, anchor bootstrap, account field updates)
without external Gmail API calls.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase

from ..application.use_cases.sync_gmail_history import SyncGmailHistory
from ..application.use_cases.sync_gmail_incremental import SyncGmailIncremental
from .common import FakeNotifier


class TestSyncGmailIncremental(TransactionCase):
    """Validate Gmail incremental orchestration invariants."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()

    def _make_gmail_account(self, *, history_id: str | None):
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
                    "gmail_last_history_id": history_id,
                    "gmail_last_error": "previous-error",
                    "backoff_until": fields.Datetime.now(),
                }
            )

    def test_execute_clears_backoff_and_records_last_sync_on_success(self):
        """Successful incremental sync clears backoff, clears last_error, and updates last_sync_at."""

        account = self._make_gmail_account(history_id="123")
        notifier = FakeNotifier()
        use_case = SyncGmailIncremental(
            self.env, notifier=notifier, lease_ttl_seconds=60
        )

        def _fake_incremental(_account, _service, _owner):
            _account.write({"gmail_last_history_id": "124"})
            return {
                "ok": True,
                "changes": True,
                "history_id": "124",
                "fetched": 1,
                "deleted": 0,
                "truncated": False,
                "new_count": 1,
            }

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.sync_gmail_incremental.gmail_build_service",
                return_value=object(),
            ),
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
        self.assertEqual(account.gmail_last_history_id, "124")
        self.assertFalse(bool(account.backoff_until))
        self.assertFalse(bool(account.gmail_last_error))
        self.assertTrue(bool(account.gmail_last_sync_at))

    def test_execute_bootstrap_path_calls_history_expired_handler(self):
        """Missing history anchor triggers history-expired handling instead of crashing."""

        account = self._make_gmail_account(history_id=False)
        notifier = FakeNotifier()
        use_case = SyncGmailIncremental(
            self.env, notifier=notifier, lease_ttl_seconds=60
        )

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.sync_gmail_incremental.gmail_build_service",
                return_value=object(),
            ),
            patch.object(
                use_case,
                "_handle_history_expired",
                return_value={"ok": True, "mode": "bootstrap"},
            ) as handler,
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
        self.assertEqual(res.get("mode"), "bootstrap")
        handler.assert_called()


class TestSyncGmailHistory(TransactionCase):
    """Validate legacy Gmail history sync orchestration invariants."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()

    def _make_gmail_account(self, *, history_id: str | None):
        server = self.FetchmailServer.create(
            {
                "name": "Gmail IMAP",
                "server_type": "imap",
                "server": "imap.gmail.com",
                "port": 993,
                "user": "gmail2@example.com",
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
                    "name": "Gmail Account 2",
                    "email": "gmail2@example.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                    "imap_caps": {"tokens": ["X-GM-EXT-1"]},
                    "gmail_last_history_id": history_id,
                    "gmail_last_error": "previous-error",
                    "backoff_until": fields.Datetime.now(),
                }
            )

    def test_execute_updates_last_sync_fields_on_success(self):
        """Successful run clears backoff, clears last_error, and updates last_sync_at."""

        account = self._make_gmail_account(history_id="123")
        use_case = SyncGmailHistory(self.env, lease_ttl_seconds=60)

        def _fake_incremental(_account, _service, _owner):
            _account.write({"gmail_last_history_id": "124"})
            return {
                "ok": True,
                "changes": True,
                "history_id": "124",
                "fetched": 0,
                "deleted": 0,
            }

        with (
            patch.object(use_case, "_get_service", return_value=object()),
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
        self.assertEqual(account.gmail_last_history_id, "124")
        self.assertFalse(bool(account.backoff_until))
        self.assertFalse(bool(account.gmail_last_error))
        self.assertTrue(bool(account.gmail_last_sync_at))

    def test_execute_bootstrap_path_calls_rebuild(self):
        """Missing history anchor triggers rebuild path."""

        account = self._make_gmail_account(history_id=False)
        use_case = SyncGmailHistory(self.env, lease_ttl_seconds=60)

        with (
            patch.object(use_case, "_get_service", return_value=object()),
            patch.object(
                use_case, "_rebuild", return_value={"ok": True, "mode": "bootstrap"}
            ) as rebuild,
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
        self.assertEqual(res.get("mode"), "bootstrap")
        rebuild.assert_called()
