from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # CIPS Integration settings
    cips_api_url = fields.Char(string='CIPS API URL', config_parameter='custom_ictpack.cips_api_url')
    cips_api_token = fields.Char(string='CIPS API Token', config_parameter='custom_ictpack.cips_api_token')
    cips_webhook_secret = fields.Char(string='CIPS Webhook Secret', config_parameter='custom_ictpack.cips_webhook_secret')