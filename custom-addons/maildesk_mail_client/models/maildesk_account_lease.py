# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk MailDesk Account Lease.

Defines Odoo ORM models and server-side APIs for MailDesk Account Lease.
Layer: odoo models.
"""

import logging

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MailDeskAccountLease(models.Model):
    """
    DB-backed time-boxed lease for mailbox accounts.

    This provides a multi-worker safe lock with TTL semantics.
    """

    _name = "maildesk.account_lease"
    _description = "MailDesk Account Lease"
    _rec_name = "account_id"
    _order = "lease_until desc"

    account_id = fields.Many2one(
        "mailbox.account", required=True, index=True, ondelete="cascade"
    )
    lease_until = fields.Datetime(required=True, index=True)
    owner = fields.Char(index=True)

    _account_id_unique = models.Constraint(
        "UNIQUE (account_id)",
        "Only one lease per account.",
    )

    @api.model
    def _default_owner(self):
        return f"uid:{self.env.uid}"

    @api.model
    def _compute_lease_until(self, ttl_seconds):
        ttl = int(ttl_seconds or 0)
        if ttl <= 0:
            ttl = 60
        return fields.Datetime.now() + relativedelta(seconds=ttl)

    @api.model
    def try_acquire(self, account_id, ttl_seconds=60, owner=None) -> bool:
        """
        Attempt to acquire a lease for an account.

        Returns True on success, False if the lease is currently held.
        """
        owner = owner or self._default_owner()
        lease_until = self._compute_lease_until(ttl_seconds)

        # Use separate cursor for atomic locking visible to other workers immediately
        with self.pool.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '0ms'")
            try:
                cr.execute(
                    """
                    INSERT INTO maildesk_account_lease
                        (account_id, lease_until, owner, create_date, write_date)
                    VALUES (%s, %s, %s, now(), now())
                    ON CONFLICT (account_id) DO UPDATE
                    SET lease_until = EXCLUDED.lease_until,
                        owner = EXCLUDED.owner,
                        write_date = now()
                    WHERE maildesk_account_lease.lease_until < now()
                    """,
                    (account_id, lease_until, owner),
                )
                return cr.rowcount == 1
            except Exception as e:
                cr.rollback()
                # Fail fast on lock contention: callers must never wait on leases.
                if getattr(e, "pgcode", None) in {"55P03", "57014"}:
                    return False
                raise

    @api.model
    def renew(self, account_id, ttl_seconds=60, owner=None) -> bool:
        """
        Renew an existing lease if it is still valid.
        """
        lease_until = self._compute_lease_until(ttl_seconds)
        with self.pool.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '0ms'")
            if owner:
                try:
                    cr.execute(
                        """
                        UPDATE maildesk_account_lease
                        SET lease_until = %s,
                            owner = %s,
                            write_date = now()
                        WHERE account_id = %s
                          AND owner = %s
                          AND lease_until >= now()
                        """,
                        (lease_until, owner, account_id, owner),
                    )
                except Exception as e:
                    cr.rollback()
                    if getattr(e, "pgcode", None) in {"55P03", "57014"}:
                        return False
                    raise
            else:
                try:
                    cr.execute(
                        """
                        UPDATE maildesk_account_lease
                        SET lease_until = %s,
                            write_date = now()
                        WHERE account_id = %s
                          AND lease_until >= now()
                        """,
                        (lease_until, account_id),
                    )
                except Exception as e:
                    cr.rollback()
                    if getattr(e, "pgcode", None) in {"55P03", "57014"}:
                        return False
                    raise
            return cr.rowcount == 1

    @api.model
    def release(self, account_id, owner=None) -> bool:
        """
        Release a lease for an account.
        """
        with self.pool.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '0ms'")
            if owner:
                try:
                    cr.execute(
                        """
                        DELETE FROM maildesk_account_lease
                        WHERE account_id = %s AND owner = %s
                        """,
                        (account_id, owner),
                    )
                except Exception as e:
                    cr.rollback()
                    if getattr(e, "pgcode", None) in {"55P03", "57014"}:
                        _logger.info(
                            "Lease release skipped due to lock contention: account_id=%s owner=%s",
                            account_id,
                            owner,
                        )
                        return False
                    raise
            else:
                try:
                    cr.execute(
                        """
                        DELETE FROM maildesk_account_lease
                        WHERE account_id = %s
                        """,
                        (account_id,),
                    )
                except Exception as e:
                    cr.rollback()
                    if getattr(e, "pgcode", None) in {"55P03", "57014"}:
                        _logger.info(
                            "Lease release skipped due to lock contention: account_id=%s",
                            account_id,
                        )
                        return False
                    raise
            return cr.rowcount > 0

    @api.model
    def reap_expired(self, batch=5000) -> int:
        """
        Remove expired leases to prevent stuck accounts.
        """
        registry = self.env.registry
        with registry.cursor() as cr:
            cr.execute(
                """
                WITH candidates AS (
                    SELECT id
                    FROM maildesk_account_lease
                    WHERE lease_until < now()
                    ORDER BY lease_until ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                DELETE FROM maildesk_account_lease
                WHERE id IN (SELECT id FROM candidates)
                """,
                (int(batch),),
            )
            deleted = cr.rowcount
        return deleted
