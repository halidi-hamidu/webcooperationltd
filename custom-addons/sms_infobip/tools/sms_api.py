import logging

from odoo import _
from odoo.addons.sms.tools.sms_api import SmsApiBase
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


class SmsApiInfobip(SmsApiBase):
    PROVIDER_TO_SMS_FAILURE_TYPE = SmsApiBase.PROVIDER_TO_SMS_FAILURE_TYPE | {
        'infobip_authentication': 'sms_credit',
        'infobip_sender_missing': 'sms_acc',
        'infobip_invalid_number': 'wrong_number_format',
    }

    def _get_infobip_client(self):
        """Initialize and return Infobip API client"""
        company_sudo = (self.company or self.env.company).sudo()
        
        if not company_sudo.sms_infobip_api_key or not company_sudo.sms_infobip_base_url:
            raise ApiException("Infobip API credentials not configured")
        
        # Ensure base URL has https:// prefix
        base_url = company_sudo.sms_infobip_base_url
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        
        _logger.debug("Infobip API - Base URL: %s, API Key starts with: %s...", 
                     base_url, company_sudo.sms_infobip_api_key[:10])
        
        client_config = Configuration(
            host=base_url,
            api_key={"APIKeyHeader": company_sudo.sms_infobip_api_key},
            api_key_prefix={"APIKeyHeader": "App"},
        )
        return ApiClient(client_config)

    def _format_phone_number(self, phone):
        """Format phone number to international format"""
        if phone:
            number = ''.join(phone.strip())
            if len(number) > 1:
                if number[0] == '0':
                    # Remove leading 0 and add country code (default: 255 for Tanzania)
                    stripped_number = number[1:]
                    formatted_number = '255' + stripped_number
                    return formatted_number
                if number[0] == '+':
                    # Remove + sign
                    stripped_number = number[1:]
                    return stripped_number
                if number[:3] == '255':
                    return number
                if number[0] not in ['0', '+', '255']:
                    # Add default country code
                    formatted_number = '255' + number
                    return formatted_number
        return phone

    def _clean_message(self, message):
        """Clean message text by removing extra whitespace"""
        message_words = message.split()
        return ' '.join(message_words)

    def _send_sms_batch(self, messages, delivery_reports_url=False):
        """Send a batch of SMS using Infobip.
        See params and returns in original method sms/tools/sms_api.py
        In addition to the uuid and state, we add the sms_infobip_message_id to the returns (one per sms)
        """
        company_sudo = (self.company or self.env.company).sudo()
        
        if not company_sudo.sms_infobip_sender_id:
            _logger.warning('Infobip Sender ID not configured')
            return [{
                'failure_reason': _("Infobip Sender ID not configured"),
                'failure_type': 'infobip_sender_missing',
                'state': 'infobip_sender_missing',
                'uuid': number_info['uuid'],
            } for message in messages for number_info in message.get('numbers', [])]

        api_client = self._get_infobip_client()
        api_instance = SmsApi(api_client)

        res = []
        for message in messages:
            body = self._clean_message(message.get('content') or '')
            for number_info in message.get('numbers') or []:
                uuid = number_info['uuid']
                to_number = self._format_phone_number(number_info['number'])
                
                fields_values = {
                    'failure_reason': _("Unknown failure at sending, please contact support"),
                    'state': 'server_error',
                    'uuid': uuid,
                }

                try:
                    sms_request = SmsRequest(
                        messages=[
                            SmsMessage(
                                destinations=[
                                    SmsDestination(to=to_number),
                                ],
                                sender=company_sudo.sms_infobip_sender_id,
                                content=SmsMessageContent(
                                    actual_instance=SmsTextContent(text=body)
                                )
                            )
                        ]
                    )
                    
                    api_response: SmsResponse = api_instance.send_sms_messages(
                        sms_request=sms_request
                    )

                    _logger.debug('Infobip SMS API response: %s', api_response)
                    
                    if api_response.messages and len(api_response.messages) > 0:
                        response_msg = api_response.messages[0]
                        
                        if response_msg.status.name in ('PENDING_ACCEPTED', 'PENDING_ENROUTE'):
                            fields_values.update({
                                'failure_reason': False,
                                'failure_type': False,
                                'sms_infobip_message_id': response_msg.message_id,
                                'state': 'sent',
                            })
                        else:
                            error_message = response_msg.status.description or "Unknown error"
                            fields_values.update({
                                'failure_reason': error_message,
                                'failure_type': 'unknown',
                                'state': 'unknown',
                            })
                    else:
                        fields_values.update({
                            'failure_reason': _("No response from Infobip"),
                            'failure_type': 'server_error',
                            'state': 'server_error',
                        })

                except ApiException as ex:
                    _logger.error('Infobip SMS API error: %s', str(ex))
                    failure_type = self._infobip_error_to_odoo_state(ex)
                    error_message = str(ex) or self._get_sms_api_error_messages().get(failure_type)
                    fields_values.update({
                        'failure_reason': error_message,
                        'failure_type': failure_type,
                        'state': failure_type,
                    })
                except Exception as e:
                    _logger.error('Unexpected error sending SMS via Infobip: %s', str(e))
                    fields_values.update({
                        'failure_reason': str(e),
                        'failure_type': 'server_error',
                        'state': 'server_error',
                    })

                res.append(fields_values)

        return res

    def _infobip_error_to_odoo_state(self, exception):
        """Map Infobip error codes to Odoo SMS failure types"""
        error_str = str(exception).lower()
        
        if 'unauthorized' in error_str or 'authentication' in error_str or '401' in error_str:
            return 'infobip_authentication'
        elif 'invalid' in error_str and 'number' in error_str:
            return 'infobip_invalid_number'
        elif 'number' in error_str and 'format' in error_str:
            return 'wrong_number_format'
        
        _logger.warning('Infobip SMS: Unknown error "%s"', error_str)
        return 'unknown'

    def _get_sms_api_error_messages(self):
        error_dict = super()._get_sms_api_error_messages()
        error_dict.update({
            'infobip_authentication': _("Infobip Authentication Error - Check your API credentials"),
            'infobip_sender_missing': _("Infobip Sender ID is required to send messages"),
            'infobip_invalid_number': _("Invalid phone number format"),
            'sms_number_missing': _("A 'To' phone number is required"),
            'wrong_number_format': _("The number you're trying to reach is not correctly formatted"),
            'unknown': _("Unknown error, please contact support"),
        })
        return error_dict
