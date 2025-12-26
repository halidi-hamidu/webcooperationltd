# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError
from num2words import num2words


class AccountPayment(models.Model):
    _inherit = "account.payment"


    cheque_no = fields.Char(string='Cheque No.',
                            default=False, copy=False, help="Cheque Number")


    amount_in_word = fields.Char(string='Amount in words', readonly=True,
                                 default=False, copy=False, compute='_compute_text'
                                 )

    def print_voucher(self):
        return self.env.ref('account.action_report_payment_receipt'). report_action(self)


    @api.depends('amount')
    def _compute_text(self):
        amount = self.amount
        if self.currency_id.name:
            currency = self.currency_id.name
        else:
            currency = self._get_currency_name()
        try:
            self.amount_in_word = num2words(amount, to='currency', separator=' and', cents=True,
                                            currency=currency, adjective=True).title()
        except NotImplementedError:
            self.amount_in_word = num2words(
                amount, to='currency', separator=' and', cents=True).title()
            self.amount_in_word = self.amount_in_word.replace(
                'Euro', 'Tanzanian Shillings')

    @api.model
    def _get_currency_name(self):
        journal = self.env['account.journal'].browse(
            self._context.get('journal_id', False))
        if journal.currency_id:
            return journal.currency_id.name
        return self.env.user.company_id.currency_id.name
