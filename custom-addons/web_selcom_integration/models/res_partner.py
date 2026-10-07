import secrets

from odoo import api, fields, models

from .selcom_client import Selcom


class ResPartner(models.Model):
    _inherit = "res.partner"

    selcom_till_alias = fields.Char(
        string="Selcom Till Alias",
        index=True,
        help="Unique Selcom till alias used to receive payments for this "
             "customer. Generated once and reused for all transactions.")
    selcom_customer_id = fields.Char(
        string="Selcom Customer ID", index=True)
    selcom_gateway_buyer_uuid = fields.Char(
        string="Selcom Gateway Buyer UUID")

    _sql_constraints = [
        ("selcom_till_alias_uniq", "unique(selcom_till_alias)",
         "This Selcom till alias is already assigned to another customer."),
    ]

    def action_generate_selcom_till_alias(self):
        for partner in self:
            alias = Selcom(partner.env).generate_till_alias(
                partner.id, existing=partner.selcom_till_alias)
            partner.write({"selcom_till_alias": alias})
