from odoo import models


class PaymentTransaction(models.Model):
    """Hook point: mark selcom.order paid when a matching payment
    transaction is confirmed through Odoo's acquirer pipeline."""
    _inherit = "payment.transaction"

    def _post_process_payment_data(self):
        res = super()._post_process_payment_data()
        for tx in self.filtered(
                lambda t: t.acquirer_id.provider == "selcom"
                and t.state == "done"):
            order = self.env["selcom.order"].sudo().search(
                [("order_id", "=", tx.reference)], limit=1)
            if order and order.state != "paid":
                order.write({"state": "paid"})
        return res
