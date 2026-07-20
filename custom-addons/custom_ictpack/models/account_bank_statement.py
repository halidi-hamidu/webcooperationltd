# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command, api, fields, models, _
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

    def edit_reconcile_line(self, move_line_id, record_data):
        self.ensure_one()
        if self.checked and self.is_reconciled and not self.move_id._is_user_able_to_review():
            raise ValidationError(_("Validated entries can only be changed by your accountant."))

        move_line_to_edit = self.env['account.move.line'].browse(move_line_id)

        if move_line_to_edit.tax_line_id and any(record_data.get(key) for key in ['tax_ids', 'partner_id', 'account_id']):
            return

        exchange_line = self.env['account.move.line']
        if (exchange_move := move_line_to_edit._get_matched_move_ids().exchange_move_id) and any(record_data.get(key) for key in ['balance', 'amount_currency']):
            exchange_line |= exchange_move.line_ids.filtered(lambda line: line in move_line_to_edit.reconciled_lines_ids)

        liquidity_lines, _suspense_lines, other_lines = self._seek_for_lines()

        original_base_lines = []
        original_tax_lines = []
        if not move_line_to_edit.reconciled_lines_ids and any(record_data.get(key) for key in ['tax_ids', 'balance', 'amount_currency']) and not move_line_to_edit.tax_line_id and not exchange_move:
            original_base_lines, original_tax_lines = self._prepare_for_tax_lines_recomputation()

        edited_move_reconciled_line_ids = (move_line_to_edit.reconciled_lines_ids - exchange_line).ids
        move_line_to_edit.remove_move_reconcile()
        move_line_to_edit_vals = move_line_to_edit._get_aml_values(**record_data)
        if edited_move_reconciled_line_ids:
            move_line_to_edit_vals['reconciled_lines_ids'] = [Command.set(edited_move_reconciled_line_ids)]

        self._set_move_line_to_statement_line_move(
            (liquidity_lines + other_lines) - move_line_to_edit,
            [move_line_to_edit_vals],
        )
        _new_liquidity_lines, new_suspense_lines, _new_other_lines = self._seek_for_lines()
        edited_line = self.line_ids - (liquidity_lines + other_lines + new_suspense_lines)

        if not edited_line.reconciled_lines_ids and any(record_data.get(key) for key in ['tax_ids', 'balance', 'amount_currency']) and not edited_line.tax_line_id and not exchange_move:
            self._edit_tax_lines(original_base_lines, original_tax_lines, edited_line, move_line_to_edit)

        if 'partner_id' in record_data and not record_data['partner_id']:
            edited_line.partner_id = False
