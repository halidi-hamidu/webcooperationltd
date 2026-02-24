# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
MailDesk UI Presence: Tracks whether user has MailDesk UI open.

Layer: odoo models
"""

from datetime import timedelta

from odoo import api, fields, models


class MailDeskUiPresence(models.Model):
    """
    MailDesk UI presence heartbeat.

    Used to gate desktop notifications (real-time only, never replayed).
    """

    _name = "maildesk.ui_presence"
    _description = "MailDesk UI Presence"
    _rec_name = "user_id"

    user_id = fields.Many2one(
        "res.users", required=True, index=True, ondelete="cascade"
    )
    last_ping_at = fields.Datetime(required=True, index=True)

    _user_uniq = models.Constraint(
        "UNIQUE (user_id)",
        "User must be unique.",
    )

    @api.model
    def ping(self) -> bool:
        """
        Mark the current user as having MailDesk open.

        Uses UPSERT to avoid serialization failures on concurrent pings.
        """
        uid = self.env.uid
        now = fields.Datetime.now()

        # Use raw SQL UPSERT to handle concurrency without serialization errors
        self.env.cr.execute(
            """
            INSERT INTO maildesk_ui_presence (user_id, last_ping_at, create_uid, write_uid, create_date, write_date)
            VALUES (%(user_id)s, %(now)s, %(user_id)s, %(user_id)s, %(now)s, %(now)s)
            ON CONFLICT (user_id) DO UPDATE SET
                last_ping_at = EXCLUDED.last_ping_at,
                write_uid = EXCLUDED.write_uid,
                write_date = EXCLUDED.write_date
            """,
            {"user_id": uid, "now": now},
        )
        return True

    @api.model
    def online_user_ids(self, user_ids, *, max_age_seconds: int) -> list[int]:
        """
        Return subset of user_ids considered 'online in MailDesk'.

        Args:
            user_ids: List of user IDs to check
            max_age_seconds: Max seconds since last ping to be considered online

        Returns:
            List of user IDs that are online
        """
        ids = [int(u) for u in (user_ids or []) if u]
        if not ids:
            return []

        cutoff = fields.Datetime.now() - timedelta(seconds=int(max_age_seconds))
        recs = (
            self.sudo()
            .search([("user_id", "in", ids), ("last_ping_at", ">=", cutoff)])
            .mapped("user_id")
        )
        return recs.ids
