from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _web_portal_has_fleet(self):
        """True when the partner (or their commercial entity) is linked to
        fleet vehicles — used for post-login redirection."""
        partner = self.commercial_partner_id or self
        if not partner:
            return False
        FleetVehicle = self.env["fleet.vehicle"]
        domain = [
            "|",
            ("driver_id", "child_of", partner.ids),
            ("manager_id", "child_of", partner.ids),
        ]
        return bool(FleetVehicle.search_count(domain))
