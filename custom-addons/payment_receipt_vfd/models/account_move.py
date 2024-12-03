from odoo import fields, models, api, exceptions, _
from datetime import datetime, date
import pytz
import re
from odoo.tools import html_escape, html_sanitize


class AccountMove(models.Model):
    _inherit = 'account.move'

    is_vfd_receipt_generated = fields.Boolean("VFD Generated", default=False, copy=False)
    vfd_receipt_ids = fields.One2many('payment.receipt.vfd', 'invoice_id', copy=False)
    payment_type_id = fields.Many2one('payment.receipt.payment.type','Payment Type', copy=False)
    tax_type_id = fields.Many2one('payment.receipt.tax.type','Tax Type', copy=False)
    identity_type_id = fields.Many2one('payment.receipt.identity.type','Identity Type', copy=False)

    def _get_exchange_rate(self, currency, date):
            rate = self.env['res.currency.rate'].search([('currency_id', '=', currency.id), ('name', '<=', date)], limit=1, order='name desc')
            return rate.rate if rate else 1

    def generate_vfd_receipt(self):
        for rec in self:
            if rec.partner_id.phone is False:
                raise exceptions.UserError('Customer Phone Number is not set.')
            receipt_no_ = rec.get_receipt_no()
            exchange_rate = 1
            if rec.currency_id.name != 'TZS':
                invoice_date = rec.invoice_date
                exchange_rate = self._get_exchange_rate(rec.currency_id, invoice_date)

            vals = {
                "invoice_id": rec.id,
                "receipt_id": rec.get_receipt_id(),
                "receipt_no": receipt_no_,
                "receipt_date": fields.date.today(),
                "receipt_time": fields.datetime.now(),
                "receipt_z_no": rec.get_z_number(),
                "customer_name": rec.partner_id.name,
                "customer_phone": rec.partner_id.phone,
                "customer_vrn": rec.partner_id.vrn or "",
                "customer_id": rec.partner_id.vat or "000000000",
                "customer_id_type": rec.identity_type_id.key,
                "verification_code": receipt_no_,
                "receipt_url": rec.get_receipt_url(receipt_no_),
                "payment_method": rec.payment_type_id.key,
                "items": [
                    {
                        'name': re.sub(r'[^A-Za-z0-9 ]+', '', x.name.replace('\n', ' ')).strip(),
                        'quantity': "1",
                        'price': str(x.price_subtotal/exchange_rate),
                        'tax': str((x.price_subtotal * rec.tax_type_id.rate)/exchange_rate),
                        'tax_type': rec.tax_type_id.key,
                        'discount': '0'
                    } for x in rec.invoice_line_ids
                ]
            }

            res = rec.env['payment.receipt.vfd'].create(vals)
            if res:
                rec.is_vfd_receipt_generated = True

    def get_receipt_url(self, receipt_no_):
        tra_url = "https://verify.tra.go.tz/"
        receipt_time = self.get_receipt_time()
        receipt_url = tra_url + str(receipt_no_) + '_' + str(receipt_time)
        return receipt_url

    def get_receipt_time(self):
        return datetime.now(pytz.timezone('Africa/Dar_es_salaam')).strftime('%H%M%S')

    def print_vfd_receipt(self):
        for rec in self:
            for url in rec.vfd_receipt_ids:
                print(url.receipt_url)
                return {
                    'name': _("VFD Receipt"),
                    'type': 'ir.actions.act_url',
                    'url': url.receipt_url,  # Replace this with tracking link
                    'target': 'new',  # you can change target to current, self, new.. etc
                }

    def get_receipt_id(self):
        vfd_daily_counter = self.get_config_param('payment_receipt_vfd.vfd_daily_counter')
        counter_latest_update = self.get_config_param('payment_receipt_vfd.counter_latest_update')
        today = date.today().strftime('%Y%m%d')

        if counter_latest_update == today:
            next_counter = int(vfd_daily_counter) + 1
            self.env['ir.config_parameter'].sudo().set_param('payment_receipt_vfd.counter_latest_update',
                                                             self.get_z_number())
            self.env['ir.config_parameter'].sudo().set_param('payment_receipt_vfd.vfd_daily_counter',
                                                             next_counter)
            return next_counter
        else:
            self.env['ir.config_parameter'].sudo().set_param('payment_receipt_vfd.counter_latest_update',
                                                             self.get_z_number())
            self.env['ir.config_parameter'].sudo().set_param('payment_receipt_vfd.vfd_daily_counter', 1)
            return 1

    def get_z_number(self):
        return date.today().strftime('%Y%m%d')

    def get_receipt_no(self):
        vfd_receipt_count = self.get_config_param('payment_receipt_vfd.vfd_receipt_count')
        verification_code = self.get_config_param('payment_receipt_vfd.verification_code')
        vfd_daily_counter = self.get_config_param('payment_receipt_vfd.vfd_daily_counter')
        if verification_code is False:
            raise exceptions.UserError('Verification Code is not Set, Please Refresh VFD settings to generate.')
        else:
            next_count = int(vfd_receipt_count) + 1
            self.env['ir.config_parameter'].sudo().set_param('payment_receipt_vfd.vfd_receipt_count',
                                                             next_count)
            return str(verification_code) + str(next_count)

    def get_config_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)

    def format_phone_number(self, phone):
        if phone:
            number = ''.join(phone.strip())

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
