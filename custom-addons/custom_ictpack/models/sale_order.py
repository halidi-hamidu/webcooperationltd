from odoo import models, fields, api, _
from num2words import num2words


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    amount_in_word = fields.Char(string='Amount in words', readonly=True,
                                 default=False, copy=False, compute='_compute_text'
                                 )

    reference_number = fields.Char(string='Reference No.', default=False, copy=False)

    reference_date = fields.Datetime(string='Reference Date', copy=False, help="Reference Date")

    date_order_temp = fields.Datetime(string='Order Date', readonly=True, store=False)

    business_line = fields.Selection([
        ('atras', 'IoT VTS'),
        ('ects', 'IoT ECTS'),
        ('itms', 'IT Management & Security Services'),
        ('uis', 'Unified Infrastructure Solutions'),
        ('ictpack', 'Application Software'),
    ], string='Business Line', default='ictpack',index=True, readonly=False, required=True, copy=False,
        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})

    @api.model
    def _get_currency_name(self):
        journal = self.env['account.journal'].browse(self._context.get('journal_id', False))
        if journal.currency_id:
            return journal.currency_id.name
        return self.env.user.company_id.currency_id.name

    @api.depends('amount_total')
    def _compute_text(self):
        currency = ''
        if self.currency_id.name:
            currency = self.currency_id.name
        else:
            currency = self._get_currency_name()
        try:
            self.amount_in_word = num2words(self.amount_total, to='currency', separator=' and', cents=True,
                                            currency=currency, adjective=True).title()
        except NotImplementedError:
            self.amount_in_word = num2words(self.amount_total, to='currency', separator=' and', cents=True).title()
            self.amount_in_word = self.amount_in_word.replace('Euro', 'Tanzanian Shillings')

    def _prepare_invoice(self):
         res = super(SaleOrder,self)._prepare_invoice()
         res['business_line'] = self.business_line
         return res

    def action_confirm(self):
        self.date_order_temp = self.date_order
        res = super(SaleOrder,self).action_confirm()
        if (res):
            self.write({
                'date_order': self.date_order_temp
            })
        return res
