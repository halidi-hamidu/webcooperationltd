import logging
from odoo import fields, models, api
from datetime import datetime, timedelta
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SmsNotification(models.Model):
    _name = 'sms.notification'
    _description = 'SMS Notifications'

    customer = fields.Many2one('res.partner')
    phone_number = fields.Char(related="customer.phone")
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
    sms_tracker_id = fields.Many2one('sms.sms', string='SMS Tracker', readonly=True)

    message_count = fields.Integer("Message Count", compute='_compute_message_count', store=True)
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

    def send_sms_notification_cron(self):
        """Cron job to send pending SMS notifications"""
        sms_obj = self.search([('state', '=', 'outgoing')])
        for rec in sms_obj:
            rec.send_again()
            rec.env.cr.commit()

    def send_sms_via_odoo(self, recipient, message):
        """Send SMS using Odoo's standard SMS API which will use sms_infobip"""
        if not recipient:
            return {'success': False, 'error': 'No phone number provided'}
        
        # Use Odoo's standard SMS sending mechanism
        # This will automatically use the sms_infobip provider
        try:
            sms = self.env['sms.sms'].sudo().create({
                'number': recipient,
                'body': message,
                'partner_id': self.customer.id if self.customer else False,
            })
            sms.send()
            return {'success': True, 'sms_id': sms.id, 'state': sms.state}
        except Exception as e:
            _logger.error("Failed to send SMS: %s", str(e))
            return {'success': False, 'error': str(e)}

    def clean_message(self, message):
        """Clean message text by removing extra whitespace"""
        message_words = message.split()
        cleaned_message = ' '.join(message_words)
        return cleaned_message

    def send_again(self):
        """Send or resend SMS notification"""
        for rec in self:
            if rec.state == 'outgoing':
                # Prepare message
                if rec.use_sms_template:
                    message = self._render_template(rec.template_id, rec.id)
                    rec.message = self.clean_message(message)
                else:
                    message = rec.message
                
                # Get recipient
                recipient = rec.phone_number
                
                if not recipient:
                    rec.no_phone_number()
                    continue
                
                # Send SMS using Odoo's standard API
                result = rec.send_sms_via_odoo(recipient, message)
                
                if result.get('success'):
                    rec.sent_to_provider(result)
                else:
                    rec.failed_to_send(result.get('error', 'Unknown error'))

    def sent_to_provider(self, result):
        """Mark SMS as sent"""
        self.sms_tracker_id = result.get('sms_id')
        self.sent_datetime = fields.Datetime.now()
        self.state = 'sent'

    def failed_to_send(self, error_message):
        """Mark SMS as failed"""
        self.state = 'error'
        self.failure_reason = str(error_message)

    def no_phone_number(self):
        """Mark SMS as failed due to missing phone number"""
        self.state = 'error'
        self.failure_reason = 'No Phone Number Was Provided'

    def update_delivery_status(self):
        """Update delivery status from linked sms.sms records"""
        for rec in self.search([('state', '=', 'sent'), ('sms_tracker_id', '!=', False)]):
            sms = rec.sms_tracker_id
            if sms.state == 'sent':
                rec.state = 'delivered'
                rec.delivered_datetime = fields.Datetime.now()
            elif sms.state in ('error', 'canceled'):
                rec.state = 'error'
                rec.failure_reason = sms.failure_reason or 'SMS delivery failed'


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
    

    @api.depends('customer')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = self.env['sms.notification'].search_count([('customer', '=', rec.customer.id)])

    def view_message(self):
        pass