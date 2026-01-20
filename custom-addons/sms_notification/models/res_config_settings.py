from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Note: Infobip configurations have been moved to sms_infobip module
    # Configure SMS provider in Settings > General Settings > Integrations > SMS
