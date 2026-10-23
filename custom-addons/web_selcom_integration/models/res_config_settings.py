from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    selcom_base_url = fields.Char(
        string="Base URL",
        config_parameter="web_selcom_integration.base_url",
        default="https://apigw.selcommobile.com/v1",
    )
    selcom_api_key = fields.Char(
        string="API Key",
        config_parameter="web_selcom_integration.api_key",
    )
    selcom_api_secret = fields.Char(
        string="API Secret",
        config_parameter="web_selcom_integration.api_secret",
    )
    selcom_vendor_till = fields.Char(
        string="Vendor Till",
        config_parameter="web_selcom_integration.vendor_till",
    )
    selcom_create_till_alias_endpoint = fields.Char(
        string="Create Till Alias Endpoint",
        config_parameter="web_selcom_integration.create_till_alias_endpoint",
        default="/checkout/create-till-alias",
    )
