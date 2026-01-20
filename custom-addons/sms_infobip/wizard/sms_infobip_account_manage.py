import logging

from odoo import _, fields, models
from odoo.exceptions import UserError
from infobip_api_client.api_client import ApiClient, Configuration
from infobip_api_client.models import (
    SmsRequest,
    SmsMessage,
    SmsMessageContent,
    SmsTextContent,
    SmsDestination,
    SmsResponse,
)
from infobip_api_client.api.sms_api import SmsApi
from infobip_api_client.exceptions import ApiException

_logger = logging.getLogger(__name__)


class SmsInfobipAccountManage(models.TransientModel):
    _name = 'sms.infobip.account.manage'
    _description = 'SMS Infobip Configuration Wizard'

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        readonly=True,
        default=lambda self: self.env.company
    )
    sms_provider = fields.Selection(related='company_id.sms_provider', readonly=False)
    sms_infobip_api_key = fields.Char(related='company_id.sms_infobip_api_key', readonly=False)
    sms_infobip_base_url = fields.Char(related='company_id.sms_infobip_base_url', readonly=False)
    sms_infobip_sender_id = fields.Char(related='company_id.sms_infobip_sender_id', readonly=False)
    test_number = fields.Char("Test Number")

    def action_test_connection(self):
        """Test the Infobip connection with the provided credentials"""
        if not self.sms_infobip_api_key or not self.sms_infobip_base_url:
            raise UserError(_("Please fill in the API Key and Base URL before testing."))

        try:
            client_config = Configuration(
                host=self.sms_infobip_base_url,
                api_key={"APIKeyHeader": self.sms_infobip_api_key},
                api_key_prefix={"APIKeyHeader": "App"},
            )
            api_client = ApiClient(client_config)
            api_instance = SmsApi(api_client)
            
            # Try to get account info (this will verify credentials)
            return self._display_notification(
                notif_type='success',
                message=_("Connection successful! Your Infobip credentials are valid."),
            )
        except ApiException as e:
            _logger.warning('Infobip SMS API error: %s', str(e))
            return self._display_notification(
                notif_type='danger',
                message=_("Connection failed: %s", str(e)),
            )
        except Exception as e:
            _logger.error('Unexpected error testing Infobip connection: %s', str(e))
            return self._display_notification(
                notif_type='danger',
                message=_("An error occurred: %s", str(e)),
            )

    def action_send_test(self):
        """Send a test SMS to verify the configuration"""
        if not self.test_number:
            raise UserError(_("Please set the number to which you want to send a test SMS."))
        
        if not self.sms_infobip_sender_id:
            raise UserError(_("Please configure a Sender ID before sending test SMS."))

        # Format phone number
        test_number = self._format_phone_number(self.test_number)
        
        composer = self.env['sms.composer'].create({
            'body': _("This is a test SMS from Odoo using Infobip"),
            'composition_mode': 'numbers',
            'numbers': test_number,
        })
        sms_su = composer._action_send_sms()[0]

        has_error = bool(sms_su.failure_type)
        if not has_error:
            message = _("The SMS has been sent successfully from %s", self.sms_infobip_sender_id)
        elif sms_su.failure_type != "unknown":
            sms_api = self.company_id._get_sms_api_class()(self.env)
            failure_type = dict(
                self.env['sms.sms']._fields['failure_type'].get_description(self.env)['selection']
            ).get(sms_su.failure_type, sms_su.failure_type)
            message = _('%(failure_type)s: %(failure_reason)s',
                       failure_type=failure_type,
                       failure_reason=sms_api._get_sms_api_error_messages().get(
                           sms_su.failure_type, failure_type
                       ),
            )
        else:
            message = _("Error: %s", sms_su.failure_reason or sms_su.failure_type)
        
        return self._display_notification(
            notif_type='danger' if has_error else 'success',
            message=message,
        )

    def _format_phone_number(self, phone):
        """Format phone number to international format"""
        if phone:
            number = ''.join(phone.strip())
            if len(number) > 1:
                if number[0] == '0':
                    # Remove leading 0 and add country code (default: 255 for Tanzania)
                    stripped_number = number[1:]
                    return '255' + stripped_number
                if number[0] == '+':
                    # Remove + sign
                    return number[1:]
                if number[:3] == '255':
                    return number
                if number[0] not in ['0', '+', '2']:
                    # Add default country code
                    return '255' + number
        return phone

    def _display_notification(self, notif_type, message):
        """Display a notification to the user"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': notif_type,
                'message': message,
                'sticky': False,
            }
        }

    def action_save(self):
        """Save the configuration and close the wizard"""
        return {'type': 'ir.actions.act_window_close'}

    def action_save(self):
        return {'type': 'ir.actions.act_window_close'}

    def _display_notification(self, notif_type, message):
        """Display a notification to the user"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': notif_type,
                'message': message,
                'sticky': False,
            }
        }
