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

    def action_confirm(self):
        self.date_order_temp = self.date_order
        res = super(SaleOrder,self).action_confirm()
        if (res):
            self.write({
                'date_order': self.date_order_temp
            })
        return res

    def _handle_automatic_invoices(self, invoice, auto_commit):
        """Override to leave subscription invoices in draft for accountant review.

        The enterprise method has two paths that post invoices:
          1. No payment token  → _process_auto_invoice() → action_post()
          2. Payment token     → invoice._post()  (after successful payment)

        Both are inside _handle_automatic_invoices, so we intercept here to
        ensure subscription invoices always stay in *draft*, regardless of
        whether the subscription uses a payment token or not.
        Non-subscription invoices (if any) are forwarded to the standard flow.
        """
        for inv in invoice:
            inv.message_post(
                body=_(
                    "Subscription invoice generated automatically and left "
                    "in Draft for accountant review."
                )
            )
        # Clear the payment_exception flag that _handle_automatic_invoices
        # normally sets at the start — we intentionally skipped posting, so
        # there is no actual exception.
        self.with_context(mail_notrack=True).payment_exception = False
        return invoice
    
    
