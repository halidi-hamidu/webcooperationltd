import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        portal_group = self.env.ref("base.group_portal", raise_if_not_found=False)
        for vals, user in zip(vals_list, users):
            if vals.get("password") and portal_group and portal_group in user.group_ids:
                # Dev helper: surface the generated/assigned portal password
                _logger.warning(
                    "[PORTAL USER] %s (login=%s) created with password: %s",
                    user.name, user.login, vals["password"],
                )
        return users

    def write(self, vals):
        res = super().write(vals)
        if vals.get("password"):
            portal_group = self.env.ref("base.group_portal", raise_if_not_found=False)
            for user in self:
                if portal_group and portal_group in user.group_ids:
                    _logger.warning(
                        "[PORTAL USER] %s (login=%s) password set to: %s",
                        user.name, user.login, vals["password"],
                    )
        return res

    def _action_welcome(self):
        """Log the signup token/url sent to newly invited portal users."""
        res = super()._action_welcome()
        for user in self:
            partner = user.sudo().partner_id
            if partner and partner.signup_valid:
                _logger.warning(
                    "[PORTAL INVITE] %s (login=%s) signup URL: %s",
                    user.name, user.login, partner.signup_url,
                )
        return res
