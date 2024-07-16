from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # InfoBip Configurations
    infobip_base_url = fields.Char("InfoBip Base URL", config_parameter='sms_notification.infobip_base_url')
    infobip_api_key = fields.Char("InfoBip API Key", config_parameter='sms_notification.infobip_api_key')
    infobip_sender_id = fields.Char("Sender ID", config_parameter='sms_notification.infobip_sender_id')
