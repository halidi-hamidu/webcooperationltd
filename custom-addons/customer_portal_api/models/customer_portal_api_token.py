import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models


class CustomerPortalApiToken(models.Model):
    """Authentication tokens for customer portal API users.

    Tokens are stored hashed (sha256) — the raw value is only ever returned
    once, at login time.
    """
    _name = "customer.portal.api.token"
    _description = "Customer Portal API Token"
    _order = "create_date desc"

    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="cascade")
    partner_id = fields.Many2one(related="user_id.partner_id", store=True)
    token_hash = fields.Char(required=True, index=True)
    expires_at = fields.Datetime(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("token_hash_uniq", "unique(token_hash)", "Token hash must be unique"),
    ]

    @api.model
    def _hash_token(self, raw_token):
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @api.model
    def create_for_user(self, user, ttl_seconds=None):
        """Create a new token for a user and return the raw token value."""
        IrConfig = self.env["ir.config_parameter"].sudo()
        ttl = ttl_seconds or int(
            IrConfig.get_param("customer_portal_api.token_ttl_seconds", 86400)
        )
        raw = secrets.token_urlsafe(48)
        # Invalidate previous tokens of this user (single-session policy)
        self.search([("user_id", "=", user.id)]).write({"active": False})
        self.create(
            {
                "user_id": user.id,
                "token_hash": self._hash_token(raw),
                "expires_at": fields.Datetime.now() + timedelta(seconds=ttl),
            }
        )
        return raw

    @api.model
    def validate_token(self, raw_token):
        """Return the user record for a valid, non-expired token or None."""
        if not raw_token:
            return None
        token = self.search(
            [("token_hash", "=", self._hash_token(raw_token)), ("active", "=", True)]
        )
        if not token:
            return None
        if fields.Datetime.now() > token.expires_at:
            token.active = False
            return None
        user = token.user_id
        if not user.active:
            return None
        return user
