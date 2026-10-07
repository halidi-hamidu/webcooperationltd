from odoo import fields, models


class SelcomOrder(models.Model):
    """Local record of every Selcom checkout order."""
    _name = "selcom.order"
    _description = "Selcom Order"
    _order = "id desc"

    name = fields.Char(default="New", copy=False, readonly=True)
    order_id = fields.Char(
        "Selcom Order ID", required=True, index=True, copy=False,
        help="The unique order id sent to Selcom (e.g. ORD-20261007-8F4A91).")
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    company_id = fields.Many2one("res.company", default=lambda self:
                                 self.env.company)
    currency_id = fields.Many2one("res.currency", required=True, default=lambda
                                  self: self.env.company.currency_id)
    amount = fields.Float(required=True)
    state = fields.Selection([
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
        ("failed", "Failed"),
    ], default="pending", index=True)
    mismatch_flag = fields.Boolean(
        "Amount/Currency Mismatch", default=False, copy=False)
    gateway_reference = fields.Char(copy=False)
    payment_token = fields.Char(copy=False)
    payment_gateway_url = fields.Char(copy=False)
    qr = fields.Char(copy=False)
    channel = fields.Char(copy=False)
    phone = fields.Char(copy=False)
    move_id = fields.Many2one("account.move", string="Invoice", copy=False)

    _sql_constraints = [
        ("order_id_uniq", "unique(order_id)",
         "A Selcom order with this order id already exists."),
    ]
