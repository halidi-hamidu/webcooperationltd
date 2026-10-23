import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .selcom_client import Selcom
from ..selcom import Client


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

    def action_create_selcom_till_alias(self):
        """Create the till alias on Selcom (POST /checkout/create-till-alias)
        and store the returned alias + customer reference."""
        icp = self.env["ir.config_parameter"].sudo()
        vendor = icp.get_param("web_selcom_integration.vendor_till", "")
        if not vendor:
            raise UserError(_("Vendor Till is not configured in Settings > Selcom."))
        client = Client.from_env(self.env)
        for partner in self:
            if not partner.name:
                raise UserError(_("The customer must have a name."))
            memo = partner.selcom_till_alias or "CUST-%s" % partner.id
            payload = {
                "vendor": vendor,
                "name": partner.name[:80],
                "memo": memo,
            }
            response = None
            error_message = False
            http_status = 0
            try:
                response = client.postFunc("/checkout/create-till-alias", payload)
            except Exception as exc:
                error_message = str(exc)
                self.env["selcom.till.alias.response"].sudo().create({
                    "partner_id": partner.id,
                    "memo": memo,
                    "state": "failed",
                    "request_payload": payload,
                    "error_message": error_message,
                })
                raise UserError(_("Selcom till alias creation failed: %s") % exc)
            success = response.get("resultcode") == "000"
            self.env["selcom.till.alias.response"].sudo().create({
                "partner_id": partner.id,
                "memo": memo,
                "state": "success" if success else "failed",
                "request_payload": payload,
                "response_payload": response,
                "error_message": False if success else response.get(
                    "message", response.get("result")),
            })
            if not success:
                raise UserError(_(
                    "Selcom till alias creation failed: %s") % response.get(
                        "message", response.get("result")))
            data = (response.get("data") or [{}])[0]
            partner.write({
                "selcom_till_alias": data.get("till_alias") or memo,
                "selcom_customer_id": data.get("till_alias")
                and response.get("reference") or partner.selcom_customer_id,
            })
