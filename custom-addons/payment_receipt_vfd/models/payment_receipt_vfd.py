import pytz
import requests
from odoo import fields, models, api, http, _
from datetime import datetime, date
import logging
import ast

_logger = logging.getLogger(__name__)


class PaymentReceiptVfd(models.Model):
    _name = 'payment.receipt.vfd'
    _description = 'Description'
    _rec_name = 'receipt_no'

    receipt_id = fields.Integer('Receipt ID')
    receipt_no = fields.Char('Receipt No')
    receipt_date = fields.Date('Receipt Date')
    receipt_time = fields.Datetime('Receipt Time')
    receipt_time_str = fields.Char('Receipt Time', compute='get_receipt_time_str')
    receipt_z_no = fields.Char('Receipt Z Number')
    customer_name = fields.Char('Customer Name')
    customer_phone = fields.Char('Customer Phone')
    customer_vrn = fields.Char('Customer VRN')
    payment_method = fields.Char('Payment Method')
    invoice_id = fields.Many2one('account.move')
    error_message = fields.Char('Error Message')
    verification_code = fields.Char('Verification Code')
    customer_id = fields.Char('Customer TIN')
    customer_id_type = fields.Char('Customer TIN Type')
    receipt_url = fields.Char('Receipt URL')
    items = fields.Char('Items')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(string='Company Currency', readonly=True,
                                          related='company_id.currency_id')
    amount_tax_signed = fields.Monetary(related='invoice_id.amount_tax_signed',string='Tax Amount',currency_field='company_currency_id')
    amount_total_signed = fields.Monetary(related='invoice_id.amount_total_signed',string='Total Amount',currency_field='company_currency_id')
    amount_untaxed_signed = fields.Monetary(related='invoice_id.amount_untaxed_signed',string='Untaxed Amount ',currency_field='company_currency_id')
    invoice_currency = fields.Many2one(string='Invoice Currency', readonly=True,
                                          related='invoice_id.currency_id')
    state = fields.Selection([
        ('draft', 'In Queue'),
        ('sent', 'Sent'),
        ('error', 'Error'),
        ('verified', 'Verified'),
        ('cancel', 'Cancelled'),
    ], default='draft', copy=False)

    # Receipt Lines if need be.
    vfd_receipts_line_ids = fields.One2many('vfd.receipt.lines', 'payment_receipt_id')

    @api.depends('receipt_time')
    @api.onchange('receipt_time')
    def get_receipt_time_str(self):
        for rec in self:
            rec.receipt_time_str = str(
                rec.receipt_time.astimezone(pytz.timezone('Africa/Dar_es_salaam')).strftime('%H:%M:%S'))

    def send_receipt_cron(self):
        records = self.search([('state', 'in', ['draft', 'error'])], order='receipt_time asc', limit=1)
        print(records)
        for rec in records:
            rec.post_receipt(rec)

    def send_receipt(self):
        for rec in self:
            rec.post_receipt(rec)

    def cancel_receipt(self):
        for rec in self:
            rec.state = 'cancel'

    def print_vfd_receipt(self):
        for rec in self:
            return {
                'name': _("VFD Receipt"),
                'type': 'ir.actions.act_url',
                'url': rec.receipt_url,  # Replace this with tracking link
                'target': 'new',  # you can change target to current, self, new.. etc
            }

    def generate_token(self):
        vfd_base_url, vfd_api_key, vfd_api_secret, x_tin, vfd_token = self.get_api_credentials()
        data = {
            'api_key': vfd_api_key,
            'api_secret': vfd_api_secret
        }
        response = requests.post(vfd_base_url + '/public/api/v1/token', json=data)
        if response.status_code == 200:
            # Update token
            self.env['ir.config_parameter'].sudo().set_param('payment_receipt_vfd.vfd_token', response.json()['token'])
            return response.json()['token'], response.json()
        else:
            _logger.error(response.json()['message'])
            _logger.error(response.json())
            return response.json()['message'], response.json()

    def get_vfd_settings(self):
        vfd_base_url, vfd_api_key, vfd_api_secret, x_tin, vfd_token = self.get_api_credentials()
        headers = {
            'Authorization': 'Bearer' + ' ' + str(vfd_token),
            'x-tin': x_tin
        }
        response = requests.post(vfd_base_url + '/public/api/v1/authenticate', headers=headers)

        if response.status_code == 200:
            return response.json()['setting'], response.json()
        if response.status_code == 401:
            _logger.error(str(response.json()['message']))
            _logger.info('Generating New Token')
            self.generate_token()
        else:
            _logger.error(str(response.json()['message']))
            return False, response.json()

    # TODO: Receipt Status to be refined
    def get_receipt_status(self):
        vfd_base_url, vfd_api_key, vfd_api_secret, x_tin, vfd_token = self.get_api_credentials()
        records = self.search([('state', '=', 'sent')])
        headers = {
            'Authorization': 'Bearer' + ' ' + str(vfd_token),
            'x-tin': x_tin
        }
        for rec in records:
            data = {
                'receipt_id': str(rec.receipt_id)
            }
            response = requests.post(vfd_base_url + '/public/api/v1/status', headers=headers, json=data)

            if response.status_code == 200:
                rec.state = 'verified'

            if response.status_code == 401:
                _logger.error(str(response.json()['message']))
                _logger.info('Generating New Token')
                self.generate_token()

            else:
                _logger.error('Failed to fetch the receipt status:' + response.text)

    def resend_receipt(self):
        for rec in self:
            rec.state = 'draft'

    def post_receipt(self, obj):
        vfd_base_url, vfd_api_key, vfd_api_secret, x_tin, vfd_token = self.get_api_credentials()
        headers = {
            'Authorization': 'Bearer' + ' ' + str(vfd_token),
            'x-tin': x_tin
        }
        for rec in obj:
            data = {
                'receipt_id': str(rec.receipt_id),
                'receipt_no': str(rec.receipt_no),
                'receipt_date': str(rec.receipt_date.strftime('%Y-%m-%d')),
                'receipt_time': str(rec.receipt_time.astimezone(pytz.timezone('Africa/Dar_es_salaam')).strftime('%H:%M:%S')),
                'receipt_z_no': str(rec.receipt_z_no),
                'customer_name': str(rec.customer_name),
                'customer_phone': str(rec.customer_phone),
                'customer_vrn': str(rec.customer_vrn) or '',
                "customer_id": str(rec.customer_id) or "",
                "customer_id_type": str(rec.customer_id_type),
                'payment_method': '5',
                'items': ast.literal_eval(rec.items)
                
            }

            response = requests.post(vfd_base_url + '/public/api/v1/receipt', headers=headers, json=data)

            if response.status_code == 200:
                rec.verification_code = response.json()['data']['VerificationCode']
                rec.receipt_url = response.json()['data']['ReceiptUrl']
                rec.state = 'sent'
                rec.env.cr.commit()
                print('Response')
                print(response.json())
                return response.json()['data']

            if response.status_code == 401:
                _logger.error(str(response.json()['message']))
                _logger.info('Generating New Token')
                self.generate_token()

            else:
                rec.state = 'error'
                rec.error_message = response.text
                rec.env.cr.commit()
                return response.text

    def get_receipt_time(self):
        return datetime.now(pytz.timezone('Africa/Dar_es_salaam')).strftime('%H:%M:%S')

    def get_receipt_date(self):
        return date.today().strftime('%Y-%m-%d')

    def get_api_credentials(self):
        vfd_base_url = self.get_config_param('payment_receipt_vfd.vfd_base_url')
        vfd_api_key = self.get_config_param('payment_receipt_vfd.vfd_api_key')
        vfd_api_secret = self.get_config_param('payment_receipt_vfd.vfd_api_secret')
        x_tin = self.get_config_param('payment_receipt_vfd.x_tin')
        vfd_token = self.get_config_param('payment_receipt_vfd.vfd_token')

        return vfd_base_url, vfd_api_key, vfd_api_secret, x_tin, vfd_token

    def get_config_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)


class VfdReceiptLines(models.Model):
    _name = 'vfd.receipt.lines'
    _description = 'VFD Receipt Lines'

    name = fields.Char('Name')
    quantity = fields.Integer('Quantity')
    price = fields.Float('Price')
    tax = fields.Float('Tax')
    tax_type = fields.Char('Tax Type')
    discount = fields.Float('Discount')
    payment_receipt_id = fields.Many2one('payment.receipt.vfd')
