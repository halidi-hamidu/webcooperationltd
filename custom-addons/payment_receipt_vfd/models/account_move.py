from odoo import fields, models, api, exceptions, _
from datetime import datetime, date
import json
import logging
import pytz
import re
from odoo.tools import html_escape, html_sanitize

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    VFD_TIMEZONE = 'Africa/Dar_es_Salaam'

    is_vfd_receipt_generated = fields.Boolean("VFD Generated", default=False, copy=False)
    vfd_receipt_ids = fields.One2many('payment.receipt.vfd', 'invoice_id', copy=False)
    payment_type_id = fields.Many2one('payment.receipt.payment.type','Payment Type', copy=False)
    tax_type_id = fields.Many2one('payment.receipt.tax.type','Tax Type', copy=False)
    identity_type_id = fields.Many2one('payment.receipt.identity.type','Identity Type', copy=False)

    def _get_exchange_rate(self, currency, date):
            rate = self.env['res.currency.rate'].search([('currency_id', '=', currency.id), ('name', '<=', date)], limit=1, order='name desc')
            return rate.rate if rate else 1
    
    def _sanitize_analytic_distribution(self):
        """Fix corrupted analytic_distribution keys on move lines.

        Some move lines have analytic_distribution keys that are
        JSON-stringified dicts (e.g. '{"1": 8399}') instead of plain
        analytic account IDs (e.g. "8399").  This extracts valid account
        IDs from such corrupted keys so that posting does not crash in
        Odoo core with ``ValueError: invalid literal for int()``.
        """
        for line in self.line_ids.filtered('analytic_distribution'):
            distribution = line.analytic_distribution
            if not isinstance(distribution, dict):
                continue
            fixed = {}
            needs_fix = False
            for key, pct in distribution.items():
                # A valid key is a comma-separated list of integer IDs.
                try:
                    for part in str(key).split(','):
                        int(part.strip())
                    fixed[str(key)] = pct
                except (ValueError, AttributeError):
                    needs_fix = True
                    _logger.warning(
                        "Corrupted analytic_distribution key %r on "
                        "account.move.line id=%s — attempting repair.",
                        key, line.id,
                    )
                    # Try to extract account IDs from the JSON string.
                    try:
                        parsed = json.loads(str(key))
                    except (json.JSONDecodeError, TypeError):
                        # Last resort: pull out bare integers with regex.
                        numbers = re.findall(r'\d+', str(key))
                        if numbers:
                            fixed[','.join(numbers)] = pct
                        continue
                    if isinstance(parsed, dict):
                        for val in parsed.values():
                            if isinstance(val, (list, tuple)):
                                fixed[','.join(str(v) for v in val)] = pct
                            else:
                                fixed[str(val)] = pct
                    elif isinstance(parsed, (int, float)):
                        fixed[str(int(parsed))] = pct
            if needs_fix:
                line.sudo().analytic_distribution = fixed or False

    def action_post(self):
        self._sanitize_analytic_distribution()
        res = super(AccountMove, self).action_post()
        for rec in self:
            if rec.move_type in ['out_invoice', 'out_refund'] and not rec.is_vfd_receipt_generated:
                today = rec._get_local_now().date()
                if rec.invoice_date != today:
                    raise exceptions.UserError(
                        _('The invoice date must be equal to today\'s date (%s). '
                          'Please adjust the invoice date before posting.') % today
                    )
                try:
                    rec.generate_vfd_receipt()
                except Exception as e:
                    # Log the error but don't block the posting
                    rec.message_post(body=f"VFD Receipt generation failed: {str(e)}")
        return res


    def _prepare_vfd_receipt_vals(self):
        """Prepare the VFD receipt values from the current invoice."""
        self.ensure_one()
        rec = self
        if not rec.partner_id.phone:
            raise exceptions.UserError('Customer Phone Number is not set.')

        exchange_rate = 1
        if rec.currency_id.name != 'TZS':
            invoice_date = rec.invoice_date
            exchange_rate = self._get_exchange_rate(rec.currency_id, invoice_date)

        def clean_name(name):
            name = name.replace('\n', ' ')
            name = re.sub(r'[^A-Za-z0-9 /{}-]+', '', name)
            return name.strip()

        return {
            "customer_name": rec.partner_id.name,
            "customer_phone": rec.partner_id.phone,
            "customer_vrn": rec.partner_id.vrn or "",
            "customer_id": rec.partner_id.vat or "000000000",
            "customer_id_type": rec.identity_type_id.key,
            "payment_method": rec.payment_type_id.key,
            "items": [
                {
                    'name': clean_name(x.name),
                    'quantity': "1",
                    'price': str(x.price_subtotal / exchange_rate),
                    'tax': str((x.price_subtotal * rec.tax_type_id.rate) / exchange_rate),
                    'tax_type': rec.tax_type_id.key,
                    'discount': '0'
                } for x in rec.invoice_line_ids
            ],
        }

    def generate_vfd_receipt(self):
        for rec in self:
            vals = rec._prepare_vfd_receipt_vals()
            receipt_no_ = rec.get_receipt_no()
            now_local = rec._get_local_now()
            vals.update({
                "invoice_id": rec.id,
                "receipt_id": rec.get_receipt_id(),
                "receipt_no": receipt_no_,
                "receipt_date": now_local.date(),
                "receipt_time": now_local.astimezone(pytz.utc).replace(tzinfo=None),
                "receipt_z_no": rec.get_z_number(),
                "verification_code": receipt_no_,
                "receipt_url": rec.get_receipt_url(receipt_no_),
            })

            res = rec.env['payment.receipt.vfd'].create(vals)
            if res:
                rec.is_vfd_receipt_generated = True

    def regenerate_vfd_receipt(self):
        """Regenerate VFD receipt by updating existing error-state receipt
        with fresh data from the invoice. Keeps receipt_no, receipt_id,
        receipt_date, receipt_time, receipt_z_no, and verification_code unchanged."""
        for rec in self:
            error_receipt = rec.vfd_receipt_ids.filtered(lambda r: r.state == 'error')
            if not error_receipt:
                raise exceptions.UserError(
                    'No VFD receipt in error state found for this invoice. '
                    'Only receipts with errors can be regenerated.'
                )
            vals = rec._prepare_vfd_receipt_vals()
            vals["receipt_url"] = rec.get_receipt_url(error_receipt[0].receipt_no)
            vals["error_message"] = False
            vals["state"] = 'draft'
            for receipt in error_receipt:
                receipt.write(vals)
                receipt.message_post(
                    body="VFD Receipt regenerated from invoice by %s" % rec.env.user.name
                )

    def get_receipt_url(self, receipt_no_):
        tra_url = "https://verify.tra.go.tz/"
        receipt_time = self.get_receipt_time()
        receipt_url = tra_url + str(receipt_no_) + '_' + str(receipt_time)
        return receipt_url

    def _get_local_now(self):
        """Return the current datetime in the Tanzanian (EAT, UTC+3) timezone.
        """
        return datetime.now(pytz.timezone(self.VFD_TIMEZONE))

    def get_receipt_time(self):
        return self._get_local_now().strftime('%H%M%S')

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
        today = self._get_local_now().strftime('%Y%m%d')

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
        return self._get_local_now().strftime('%Y%m%d')

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
