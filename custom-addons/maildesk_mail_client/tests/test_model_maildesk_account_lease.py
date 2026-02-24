# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Model tests for `models/maildesk_account_lease.py`.

Focus:
- Lease reaping must be transactionally isolated (no self-deadlock).
- Lease acquisition must be fail-fast under row lock contention.
Layer: tests.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from odoo import api, fields
from odoo.tests.common import TransactionCase


class TestMailDeskAccountLease(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Lease = cls.env["maildesk.account_lease"].sudo()

    def _make_account(self, email: str):
        # Lease methods (and this test) operate with multiple cursors, so create
        # the account in a committed transaction to satisfy FK constraints.
        with self.env.registry.cursor() as cr:
            env2 = api.Environment(cr, self.env.uid, {})
            server = (
                env2["fetchmail.server"]
                .sudo()
                .create(
                    {
                        "name": "IMAP Server",
                        "server_type": "imap",
                        "server": "imap.example.com",
                        "port": 993,
                        "user": email,
                        "password": "secret",
                        "is_ssl": True,
                    }
                )
            )
            with patch(
                "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
                return_value=None,
            ):
                acc = (
                    env2["mailbox.account"]
                    .sudo()
                    .create(
                        {
                            "name": email,
                            "email": email,
                            "owner_id": env2.user.id,
                            "access_user_ids": [(6, 0, [env2.user.id])],
                            "mail_server_id": server.id,
                        }
                    )
                )
                acc_id = acc.id

        return self.env["mailbox.account"].browse(acc_id)

    def _insert_expired_lease(self, account_id: int, *, owner: str = "test") -> None:
        """
        Insert/overwrite an expired lease in a committed transaction so we can
        safely test multi-cursor lock behavior.
        """
        expired = fields.Datetime.now() - timedelta(minutes=10)
        with self.env.registry.cursor() as cr:
            cr.execute(
                """
                INSERT INTO maildesk_account_lease
                    (account_id, lease_until, owner, create_date, write_date)
                VALUES (%s, %s, %s, now(), now())
                ON CONFLICT (account_id) DO UPDATE
                SET lease_until = EXCLUDED.lease_until,
                    owner = EXCLUDED.owner,
                    write_date = now()
                """,
                (int(account_id), expired, owner),
            )

    def test_reap_expired_is_transactionally_isolated(self):
        """
        Regression: `reap_expired()` must not leave an uncommitted DELETE that
        blocks `try_acquire()` (which runs in its own cursor/transaction).
        """
        acc = self._make_account("lease-reap@example.com")
        self._insert_expired_lease(acc.id, owner="expired")

        deleted = self.Lease.reap_expired(batch=1000)
        self.assertGreaterEqual(deleted, 1)

        acquired = self.Lease.try_acquire(acc.id, ttl_seconds=60, owner="new-owner")
        self.assertTrue(acquired)

    def test_try_acquire_fails_fast_on_row_lock_contention(self):
        """
        If another transaction holds a row lock on the lease, acquisition must
        fail-fast (return False) rather than blocking the caller.
        """
        acc = self._make_account("lease-lock@example.com")
        self._insert_expired_lease(acc.id, owner="expired")

        with self.env.registry.cursor() as cr_lock:
            cr_lock.execute(
                """
                SELECT id
                FROM maildesk_account_lease
                WHERE account_id = %s
                FOR UPDATE
                """,
                (acc.id,),
            )
            acquired = self.Lease.try_acquire(acc.id, ttl_seconds=60, owner="contender")
            self.assertFalse(acquired)

        acquired_after = self.Lease.try_acquire(
            acc.id, ttl_seconds=60, owner="contender"
        )
        self.assertTrue(acquired_after)
