from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    sms_provider = fields.Selection(related='company_id.sms_provider', required=True, readonly=False)
    
    # Infobip Configuration
    sms_infobip_api_key = fields.Char(
        string="Infobip API Key",
        related='company_id.sms_infobip_api_key',
        readonly=False,
        groups='base.group_system'
    )
    sms_infobip_base_url = fields.Char(
        string="Infobip Base URL",
        related='company_id.sms_infobip_base_url',
        readonly=False,
        groups='base.group_system'
    )
    sms_infobip_sender_id = fields.Char(
        string="Infobip Sender ID",
        related='company_id.sms_infobip_sender_id',
        readonly=False,
        groups='base.group_system'
    )

    def action_open_sms_infobip_account_manage(self):
        return self.company_id._action_open_sms_infobip_account_manage()
