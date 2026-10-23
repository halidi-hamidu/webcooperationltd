"""Response log models for Selcom API interactions.

Two dedicated models store the *exact* JSON payload sent to Selcom and the
*exact* JSON response returned by Selcom, for both successful and failed
requests (whenever a response was received). No field is added, removed or
transformed — payloads are stored verbatim for auditing/troubleshooting.

Access is restricted to administrators only (see
security/ir.model.access.csv).
"""
from odoo import api, fields, models


class SelcomTillAliasResponse(models.Model):
    _name = "selcom.till.alias.response"
    _description = "Selcom Till Alias Response"
    _order = "create_date desc, id desc"

    partner_id = fields.Many2one(
        "res.partner", string="Customer", index=True, ondelete="set null",
        help="Customer (res.partner) for which the till alias request was sent.")
    memo = fields.Char(
        string="Memo", index=True,
        help="The memo/alias value included in the request payload.")
    endpoint = fields.Char(
        string="Endpoint", default="/checkout/create-till-alias", readonly=True)
    state = fields.Selection(
        [("success", "Success"), ("failed", "Failed")],
        string="Status", required=True, index=True, default="success",
        help="Success: Selcom returned resultcode 000.\n"
             "Failed: Selcom returned an error, or the request raised an "
             "exception before/while receiving a response.")
    request_payload = fields.Json(
        string="Request Payload JSON", readonly=True,
        help="Complete JSON payload exactly as sent to Selcom.")
    response_payload = fields.Json(
        string="Response JSON", readonly=True,
        help="Complete JSON response exactly as returned by Selcom. Empty "
             "when no response was received (e.g. timeout / connection error).")
    error_message = fields.Text(
        string="Error Message",
        help="Human-readable error when the request failed.")
    http_status = fields.Integer(
        string="HTTP Status", help="HTTP status code of the response, if any.")

    def action_open_related_partner(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "res_id": self.partner_id.id,
            "views": [[False, "form"]],
            "target": "current",
        }


class SelcomOrderResponse(models.Model):
    _name = "selcom.order.response"
    _description = "Selcom Order Response"
    _order = "create_date desc, id desc"

    order_id = fields.Char(
        string="Order ID", index=True, required=True,
        help="Selcom order identifier included in the request payload.")
    selcom_webhook_id = fields.Many2one(
        "selcom.webhook", string="Selcom Webhook Record", index=True,
        ondelete="set null",
        help="Matching local webhook/order record, when one exists.")
    endpoint = fields.Char(
        string="Endpoint", readonly=True,
        help="Selcom endpoint that was called, e.g. /checkout/create-order.")
    state = fields.Selection(
        [("success", "Success"), ("failed", "Failed")],
        string="Status", required=True, index=True, default="success",
        help="Success: Selcom returned resultcode 000.\n"
             "Failed: Selcom returned an error, or the request raised an "
             "exception before/while receiving a response.")
    request_payload = fields.Json(
        string="Request Payload JSON", readonly=True,
        help="Complete JSON payload exactly as sent to Selcom.")
    response_payload = fields.Json(
        string="Response JSON", readonly=True,
        help="Complete JSON response exactly as returned by Selcom. Empty "
             "when no response was received (e.g. timeout / connection error).")
    error_message = fields.Text(
        string="Error Message",
        help="Human-readable error when the request failed.")
    http_status = fields.Integer(
        string="HTTP Status", help="HTTP status code of the response, if any.")
    gateway_reference = fields.Char(
        string="Gateway Reference", index=True,
        help="Reference returned by Selcom, if any.")

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        # Best-effort link to the local webhook record.
        if rec.order_id and not rec.selcom_webhook_id:
            webhook = self.env["selcom.webhook"].sudo().search(
                [("order_id", "=", rec.order_id)], limit=1)
            if webhook:
                rec.selcom_webhook_id = webhook
        return rec

    def action_open_related_webhook(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "selcom.webhook",
            "res_id": self.selcom_webhook_id.id,
            "views": [[False, "form"]],
            "target": "current",
        }
