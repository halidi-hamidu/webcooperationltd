import logging
from odoo import fields, models, api
from datetime import datetime, timedelta
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from infobip_api_client.api_client import ApiClient, Configuration
from infobip_api_client.model.sms_advanced_textual_request import SmsAdvancedTextualRequest
from infobip_api_client.model.sms_destination import SmsDestination
from infobip_api_client.model.sms_response import SmsResponse
from infobip_api_client.model.sms_textual_message import SmsTextualMessage
from infobip_api_client.api.send_sms_api import SendSmsApi
from infobip_api_client.exceptions import ApiException

_logger = logging.getLogger(__name__)


class SmsNotification(models.Model):
    _name = 'sms.notification'
    _description = 'SMS Notifications'

    customer = fields.Many2one('res.partner')
    phone_number = fields.Char(related="customer.phone")
    mobile_number = fields.Char(related="customer.mobile")
    message = fields.Char('Message',sanitize=True)
    body_html = fields.Html('Rich-text Contents', sanitize=True, help="Rich-text/HTML message")
    failure_reason = fields.Char('Failure Reason', copy=False)
    delivered_datetime = fields.Datetime("Delivered Date")
    sent_datetime = fields.Datetime("Sent Date")
    sent_message_count = fields.Integer("Sent Messages Count")
    use_sms_template = fields.Boolean("Use SMS Template", default=False)
    template_id = fields.Many2one('sms.template')
    invoice_id = fields.Many2one('account.move', domain=[('business_line', '=', 'atras')])
    invoice_date = fields.Date(related='invoice_id.invoice_date')
    message_id_from_infobip = fields.Char('Message ID from InfoBip')
    after_sent_state = fields.Char('Status From Provider', copy=False)
    type = fields.Selection([
        ('new', 'New Registration'),
        ('30days', '30 Days Before Invoice Date'),
        ('15days', '15 Days Before Invoice Date'),
        ('due', 'Due Date'),
        ('7days', '7 Days After Invoice Date'),
        ('above7', 'Above 7 Days After Due Date'),
        ('other', 'Other')

    ], 'SMS Type', default='new', required=True)
    state = fields.Selection([
        ('outgoing', 'In Queue'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('error', 'Error'),
        ('canceled', 'Canceled')
    ], 'SMS Status', readonly=True, copy=False, default='outgoing', required=True)

    def format_phone_number(self, phone):
        if phone:
            number = ''.join(phone.strip())
            if len(number) > 1:
                if number[0] == '0':
                    stripped_number = number[1:]
                    formatted_number = '255' + stripped_number
                    return formatted_number

                if number[0] == '+':
                    stripped_number = number[1:]
                    return stripped_number

                if number[:3] == '255':
                    return number

                if number[0] not in ['0', '+', '255']:
                    formatted_number = '255' + number
                    return formatted_number
        else:
            return False

    def send_sms_notification_cron(self):
        sms_obj = self.search([('state', '=', 'outgoing')])
        for rec in sms_obj:
            rec.send_again()
            rec.env.cr.commit()

    def send_with_infobip(self, recipient, message):
        API_KEY, BASE_URL, SENDER = self.api_credentials()
        RECIPIENT = str(self.format_phone_number(recipient))
        MESSAGE_TEXT = self.clean_message(message)

        client_config = Configuration(
            host=BASE_URL,
            api_key={"APIKeyHeader": API_KEY},
            api_key_prefix={"APIKeyHeader": "App"},
        )

        api_client = ApiClient(client_config)

        sms_request = SmsAdvancedTextualRequest(
            messages=[
                SmsTextualMessage(
                    destinations=[
                        SmsDestination(
                            to=RECIPIENT,
                        ),
                    ],
                    _from=SENDER,
                    text=MESSAGE_TEXT,
                )
            ])

        api_instance = SendSmsApi(api_client)

        try:
            api_response: SmsResponse = api_instance.send_sms_message(sms_advanced_textual_request=sms_request)
            return api_response
        except ApiException as ex:
            _logger.error(ex)
            return ex

    def clean_message(self, message):
        message_words = message.split()
        cleaned_message = ' '.join(message_words)
        return cleaned_message

    def api_credentials(self):
        BASE_URL = self.env['ir.config_parameter'].sudo().get_param('sms_notification.infobip_base_url')
        API_KEY = self.env['ir.config_parameter'].sudo().get_param('sms_notification.infobip_api_key')
        SENDER = self.env['ir.config_parameter'].sudo().get_param('sms_notification.infobip_sender_id')
        return API_KEY, BASE_URL, SENDER

    def send_again(self):
        for rec in self:
            if rec.state == 'outgoing':
                if rec.use_sms_template:
                    message = self._render_template(rec.template_id, rec.id)
                    recipient = rec.phone_number or rec.mobile_number
                    rec.message = self.clean_message(message)
                    if recipient:
                        response = self.send_with_infobip(recipient, message)
                        if not isinstance(response, ApiException):
                            self.sent_to_provider(rec, response)
                        else:
                            self.failed_to_send(rec, response)
                    else:
                        self.no_phone_number(rec)
                else:
                    recipient = rec.phone_number or rec.mobile_number
                    response = self.send_with_infobip(recipient, rec.message)
                    if recipient:
                        if not isinstance(response, ApiException):
                            self.sent_to_provider(rec, response)
                        else:
                            self.failed_to_send(rec, response)
                    else:
                        self.no_phone_number(rec)

    def sent_to_provider(self, rec, response):
        if response.messages[0].status.name == 'PENDING_ACCEPTED':
            rec.message_id_from_infobip = response.messages[0].message_id
            rec.sent_datetime = fields.datetime.now()
            rec.state = 'sent'

    def failed_to_send(self, rec, response):
        rec.state = 'error'
        rec.failure_reason = response

    def no_phone_number(self, rec):
        rec.state = 'error'
        rec.failure_reason = 'No Phone Number Was Provided'

    def get_delivered_reports_from_provider(self):
        API_KEY, BASE_URL, SENDER = self.api_credentials()
        client_config = Configuration(
            host=BASE_URL,
            api_key={"APIKeyHeader": API_KEY},
            api_key_prefix={"APIKeyHeader": "App"},
        )
        api_client = ApiClient(client_config)
        api_instance = SendSmsApi(api_client)

        today = datetime.today().date()
        thirty_days_ago = today - timedelta(days=30)
        message_obj = self.search([('state', '=', 'sent'),('create_date', '>=', thirty_days_ago), ('create_date', '<=', today)], limit=100)

        for rec in message_obj:
            api_response = api_instance.get_outbound_sms_message_delivery_reports(
                message_id=rec.message_id_from_infobip, limit=2)

            if len(api_response.results) != 0:
                if api_response.results[0].status.name == 'DELIVERED_TO_HANDSET':
                    formatted_datetime = api_response.results[0].done_at.strftime(
                        DEFAULT_SERVER_DATETIME_FORMAT)
                    rec.delivered_datetime = formatted_datetime
                    rec.state = 'delivered'
                    rec.env.cr.commit()
                else:
                    logs = api_instance.get_outbound_sms_message_logs(message_id=[rec.message_id_from_infobip])
                    rec.after_sent_state = api_response


    def mark_outgoing(self):
        for rec in self:
            rec.state = 'outgoing'
            rec.sent_datetime = False
            rec.after_sent_state = False

    def cancel(self):
        for rec in self:
            rec.state = 'canceled'

    def _render_template(self, template, res_ids):
        message =  self.env['sms.template']._render_template(template.body, template.model,[res_ids])
        key_value = list(message)[0]
        return message[key_value]
