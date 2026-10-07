import datetime

from odoo import api, fields, models


class LoginAttempt(models.Model):
    """Track failed login attempts for brute-force protection."""
    _name = "customer.portal.api.login.attempt"
    _description = "Customer Portal API Login Attempt"

    login = fields.Char(required=True, index=True)
    ip = fields.Char(index=True)
    successful = fields.Boolean(default=False)
    attempt_date = fields.Datetime(default=fields.Datetime.now, index=True)

    @api.model
    def register(self, login, ip, successful):
        self.create(
            {"login": login or "", "ip": ip or "", "successful": successful}
        )

    def _is_limited(self, key, window_minutes=None, max_attempts=None):
        """Check whether the given key ('login:...' or 'ip:...') has exceeded
        the failed-attempt threshold within the time window."""
        IrConfig = self.env["ir.config_parameter"].sudo()
        window = window_minutes or int(
            IrConfig.get_param("customer_portal_api.rate_limit_window_minutes", 15)
        )
        limit = max_attempts or int(
            IrConfig.get_param("customer_portal_api.rate_limit_max_attempts", 10)
        )
        kind, _, value = key.partition(":")
        since = fields.Datetime.now() - datetime.timedelta(minutes=window)
        return (
            self.search_count(
                [
                    (kind, "=", value),
                    ("successful", "=", False),
                    ("attempt_date", ">=", since),
                ]
            ) >= limit
        )
