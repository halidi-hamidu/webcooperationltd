from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    selcom_till_alias_partner = fields.Char(
        string="Selcom Till Alias (Contact)",
        related="partner_id.selcom_till_alias",
        help="Selcom till alias taken directly from the customer's contact "
             "record.")
