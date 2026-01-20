from odoo import fields, models, _
from odoo.exceptions import UserError

from odoo.addons.sms_infobip.tools.sms_api import SmsApiInfobip


class ResCompany(models.Model):
    _inherit = 'res.company'

    sms_provider = fields.Selection(
        string='SMS Provider',
        selection=[
            ('iap', 'Send via Odoo'),
            ('infobip', 'Send via Infobip'),
        ],
        default='iap',
    )
    
    # Infobip Configuration
    sms_infobip_api_key = fields.Char(
        string="Infobip API Key",
        groups='base.group_system',
        help="API Key from your Infobip account"
    )
    sms_infobip_base_url = fields.Char(
        string="Infobip Base URL",
        groups='base.group_system',
        default='https://api.infobip.com',
        help="Base URL for Infobip API (e.g., https://api.infobip.com)"
    )
    sms_infobip_sender_id = fields.Char(
        string="Infobip Sender ID",
        groups='base.group_system',
        help="Sender ID or phone number to use when sending SMS"
    )

    def _get_sms_api_class(self):
        self.ensure_one()
        if self.sms_provider == 'infobip':
            return SmsApiInfobip
        return super()._get_sms_api_class()

    def _assert_infobip_credentials(self):
        """Validate Infobip credentials"""
        self.ensure_one()
        if not self.sms_infobip_api_key:
            raise UserError(_("Infobip API Key is required. Please configure it in Settings > General Settings > SMS."))
        if not self.sms_infobip_base_url:
            raise UserError(_("Infobip Base URL is required. Please configure it in Settings > General Settings > SMS."))
        if not self.sms_infobip_sender_id:
            raise UserError(_("Infobip Sender ID is required. Please configure it in Settings > General Settings > SMS."))

    def _action_open_sms_infobip_account_manage(self):
        """Open Infobip configuration wizard"""
        return {
            'name': _('Manage Infobip SMS'),
            'res_model': 'sms.infobip.account.manage',
            'res_id': False,
            'context': self.env.context,
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'target': 'new',
        }
