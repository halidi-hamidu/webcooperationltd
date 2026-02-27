import re
import pytz
import requests
from bs4 import BeautifulSoup
from requests_html import HTMLSession
from odoo import fields, models, api, http, _
from datetime import datetime, date
import logging
import ast

_logger = logging.getLogger(__name__)


class PaymentReceiptVfd(models.Model):
    _name = 'payment.receipt.vfd'
    _description = 'Description'
    _rec_name = 'receipt_no'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    receipt_id = fields.Integer('Receipt ID')
    receipt_no = fields.Char('Receipt No')
    receipt_sequence = fields.Integer('Receipt Sequence')
    receipt_date = fields.Date('Receipt Date')
    receipt_time = fields.Datetime('Receipt Time')
    receipt_time_str = fields.Char('Receipt Time', compute='get_receipt_time_str')
    receipt_z_no = fields.Char('Receipt Z Number')
    customer_name = fields.Char('Customer Name')
    customer_phone = fields.Char('Customer Phone')
    customer_vrn = fields.Char('Customer VRN')
    payment_method = fields.Char('Payment Method')
    invoice_id = fields.Many2one('account.move')
    business_line = fields.Selection([
        ('atras', 'IoT VTS'),
        ('ects', 'IoT ECTS'),
        ('itms', 'IT Management & Security Services'),
        ('uis', 'Unified Infrastructure Solutions'),
        ('ictpack', 'Application Software'),
    ], string='Business Line',readonly=True, related="invoice_id.business_line")
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
    sequence_produced = fields.Boolean(default=False)

    ###VALUES FROM INVOICE
    amount_tax_signed = fields.Monetary(related='invoice_id.amount_tax_signed',string='Tax Amount',currency_field='company_currency_id')
    amount_total_signed = fields.Monetary(related='invoice_id.amount_total_signed',string='Total Amount',currency_field='company_currency_id')
    amount_untaxed_signed = fields.Monetary(related='invoice_id.amount_untaxed_signed',string='Untaxed Amount ',currency_field='company_currency_id')
    invoice_currency = fields.Many2one(string='Invoice Currency', readonly=True,
                                          related='invoice_id.currency_id')
    
    ######VALUES FROM TRA
    total_excl_tax = fields.Monetary(string='TRA Total Excl Tax', currency_field='company_currency_id',readonly=True)
    total_tax = fields.Monetary(string='TRA Tax Amount', currency_field='company_currency_id',readonly=True)
    total_incl_tax = fields.Monetary(string='TRA Total Incl Tax', currency_field='company_currency_id',readonly=True)

    ######DIFFERENCES BETWEEN INVOICE & TRA
    base_amount_diff = fields.Monetary(string='Base Amount Diff', currency_field='company_currency_id',readonly=True)
    tax_amount_diff = fields.Monetary(string='Tax Amount Diff', currency_field='company_currency_id',readonly=True)
    

    state = fields.Selection([
        ('draft', 'In Queue'),
        ('sent', 'Sent'),
        ('verified', 'Posted to eFDMS'),
        ('reconcilled', 'Matching'),
        ('diff', 'Different'),
        ('error', 'Error'),
        ('missing', 'Missing'),
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
                rec.env.cr.commit()

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
    
    def verify_receipt_cron(self):
        records = self.search([('state', 'in', ['verified'])], order='receipt_time asc', limit=10)
        for rec in records:
            rec.post_receipt_efdms(rec)
    
    def verify_missing_receipt_cron(self):
        records = self.search([('state', 'in', ['missing'])], order='receipt_time desc', limit=10)
        for rec in records:
            rec.post_receipt_efdms(rec)

    def get_receipt_sequence_cron(self):
        records = self.search([('sequence_produced', '=', False)])
        for rec in records:
            verification_code_base = self.get_config_param('payment_receipt_vfd.verification_code_base')
            rec.receipt_sequence= int(rec.receipt_no.replace(verification_code_base,""))
            if rec.receipt_sequence:
                rec.sequence_produced = True

    def verify_receipt(self):
        for rec in self:
            rec.post_receipt_efdms(rec)

    def reset_receipt(self):
        for rec in self:
            rec.state = 'verified'

    def _fetch_tra_totals(self, receipt_url):
        """
        Fetch TOTAL EXCL OF TAX, TOTAL TAX, TOTAL INCL OF TAX from TRA.

        Flow (confirmed working):
          1. GET /Home/Index  → grab SESSION cookie + CSRF token
          2. POST /Home/Index with rctVcode → establishes session bound to that receipt
          3. GET /Verify/Verified?Secret=HH:MM:SS → returns full receipt HTML

        receipt_url format: https://verify.tra.go.tz/<VCODE>_<HHMMSS>
        e.g.               https://verify.tra.go.tz/8735FB2084_111417

        Returns dict {'total_excl_tax': float, 'total_tax': float, 'total_incl_tax': float}
        or None if receipt not found / parsing failed.
        """
        from urllib.parse import quote

        tra_base = 'https://verify.tra.go.tz'

        # --- parse receipt_url ---
        url_path = receipt_url.rstrip('/').split('/')[-1]  # "8735FB2084_111417"
        parts    = url_path.split('_')
        vcode    = parts[0]                                # "8735FB2084"
        time_raw = parts[-1] if len(parts) > 1 else ''    # "111417"
        secret   = ':'.join(time_raw[i:i+2] for i in range(0, 6, 2)) if len(time_raw) == 6 else ''

        _logger.info("VFD verify | vcode=%s | secret=%s", vcode, secret)

        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept':     'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })

        # Step 1 – GET home page to get SESSION cookie + CSRF token
        home = session.get(tra_base + '/Home/Index', timeout=30)
        home.raise_for_status()
        csrf_token = ''
        token_el = BeautifulSoup(home.text, 'html.parser').find(
            'input', {'name': 'requestVerificationToken'})
        if token_el:
            csrf_token = token_el['value']

        # Step 2 – POST vcode (no redirect follow) to bind session to this receipt
        session.post(
            tra_base + '/Home/Index',
            data={'requestVerificationToken': csrf_token, 'rctVcode': vcode},
            headers={'Referer': tra_base + '/Home/Index'},
            allow_redirects=False,
            timeout=30,
        )

        # Step 3 – GET /Verify/Verified?Secret=HH:MM:SS  (the actual receipt data endpoint)
        verified_url = f'{tra_base}/Verify/Verified?Secret={quote(secret)}'
        resp = session.get(verified_url, timeout=30, headers={'Referer': receipt_url})
        resp.raise_for_status()

        _logger.info("VFD verify | verified_url=%s | status=%s", verified_url, resp.status_code)

        # --- keyword-based extraction (no table dependency) ---
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Check it is actually a receipt page, not "Missing Receipt"
        if 'START OF LEGAL RECEIPT' not in resp.text:
            _logger.warning("VFD verify | vcode=%s | receipt not found on TRA", vcode)
            return None

        def extract_value(keyword):
            """Find <th>KEYWORD...</th><td ...>VALUE</td> and return float VALUE."""
            th = soup.find(lambda t: t.name == 'th' and keyword in t.get_text(strip=True).upper())
            if not th:
                return None
            td = th.find_next_sibling('td') or (th.parent.find('td') if th.parent else None)
            if not td:
                return None
            raw = td.get_text(strip=True).replace(',', '')
            try:
                return float(re.sub(r'[^\d.\-]', '', raw))
            except ValueError:
                return None

        toet = extract_value('TOTAL EXCL OF TAX')
        tox  = extract_value('TOTAL TAX')
        toit = extract_value('TOTAL INCL OF TAX')

        _logger.info("VFD verify | vcode=%s | toet=%s | tox=%s | toit=%s", vcode, toet, tox, toit)

        if toet is None or tox is None or toit is None:
            _logger.warning("VFD verify | vcode=%s | could not parse one or more totals", vcode)
            return None

        return {'total_excl_tax': toet, 'total_tax': tox, 'total_incl_tax': toit}

    def post_receipt_efdms(self, obj):
        for rec in obj:
            try:
                totals = self._fetch_tra_totals(rec.receipt_url)

                if totals is None:
                    rec.state = 'missing'
                else:
                    rec.total_excl_tax  = totals['total_excl_tax']
                    rec.total_tax       = totals['total_tax']
                    rec.total_incl_tax  = totals['total_incl_tax']

                    rec.base_amount_diff = rec.amount_untaxed_signed - rec.total_excl_tax
                    rec.tax_amount_diff  = rec.amount_tax_signed     - rec.total_tax

                    if rec.base_amount_diff == 0 and rec.tax_amount_diff == 0:
                        rec.state = 'reconcilled'
                    else:
                        rec.state = 'diff'

            except Exception as e:
                _logger.error("VFD verify | receipt=%s | error: %s", rec.receipt_no, e)
                rec.state = 'error'

            rec.env.cr.commit()


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

class PaymentReceiptMissing(models.Model):
    _name = 'payment.receipt.missing'
    _description = 'Missing Payment Receipt'

    name = fields.Char('Receipt No',required=True)

    _sql_constraints = [('name_unique', 'unique(name)','Can not add same receipt Twice!')]

    def get_missing_receipt_cron(self):
        records = self.env['payment.receipt.vfd'].search_read([],['receipt_sequence'])
        list_of_seq = []
        for rec in records:
            list_of_seq.append(rec['receipt_sequence'])
        missing_receipt = self.find_missing_entry(list_of_seq)
        if missing_receipt:
            verification_code_base = self.get_config_param('payment_receipt_vfd.verification_code_base')
            for receipt in missing_receipt:
                if not self.check_exists(str(receipt)):
                    self.create({'name': verification_code_base + str(receipt)})

    def find_missing_entry(self,sequence):
        if sequence:
            expected_sequence = range(min(sequence), max(sequence) + 1)
            missing_entries = set(expected_sequence) - set(sequence)
            if missing_entries:
                return list(missing_entries)
            else:
                return None
        else:
            return None
        
    def check_exists(self,receipt_code):
        verification_code_base = self.get_config_param('payment_receipt_vfd.verification_code_base')
        return self.search([('name','=',verification_code_base + receipt_code)])
        
    def get_config_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)
    
