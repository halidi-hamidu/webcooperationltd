# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import ustr
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError

class AccountBankStatement(models.Model):
    _inherit = "account.bank.statement"

    validated_by = fields.Many2one('res.users', 'Validated by', states={'confirm': [('readonly', True)]})

    def check_confirm_bank(self):
        res = super(AccountBankStatement, self).check_confirm_bank()
        if res:
            self.write({'validated_by': self.env.user.id})


    def button_print_statement(self):
        """ Print the bank statement, so that we can see more
        """
        if self.state == 'confirm':
            return self.env.ref('custom_ictpack.action_report_account_statement').report_action(self)
        else:
            raise UserError(_('Only Validated Bank statements can be printed from the system!'))