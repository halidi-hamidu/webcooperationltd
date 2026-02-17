# -*- coding: utf-8 -*-
#############################################################################
#
#    IctPack Solutions Ltd.
#
#    Copyright (C) 2022-TODAY IctPack Solutions Ltd
#    Author: IctPack Solutions Ltd
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        if self.move_type == 'entry':
            return super().action_post()
        else:
            indicator = True
            for line in self.invoice_line_ids:
                if line.budget_analytic_id.budget_type in ('expense', 'project'):
                    total_sum = line.price_subtotal
                    for sm in self.invoice_line_ids:
                        if (sm.budget_line_id == line.budget_line_id) and (sm.id != line.id):
                            total_sum += line.price_subtotal

                    if line.budget_line_id.allocated_balance >= total_sum:
                        indicator = True
                    else:
                        indicator = False

            if indicator:
                return super().action_post()
            else:
                raise ValidationError(_(
                    "Can not Authorize the invoice, as the Budget line(s) chosen "
                    "do not have enough funds or No Budget Lines have been added"))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    budget_type_filter = fields.Selection(
        selection=[('revenue', 'Revenue'), ('expense', 'Expense')],
        compute='_compute_budget_type_filter',
        string='Budget Type Filter',
    )
    budget_analytic_id = fields.Many2one(
        'budget.analytic', 'Budget',
        domain="[('state', '=', 'confirmed'), ('budget_type', '=?', budget_type_filter)]")
    budget_line_id = fields.Many2one(
        'budget.line', 'Budget Line',
        domain="[('budget_analytic_state', '=', 'confirmed'), ('budget_analytic_id', '=?', budget_analytic_id), ('budget_analytic_id.budget_type', '=?', budget_type_filter)]")

    @api.depends('move_type')
    def _compute_budget_type_filter(self):
        for line in self:
            if line.move_type in ('out_invoice', 'out_refund'):
                line.budget_type_filter = 'revenue'
            elif line.move_type in ('in_invoice', 'in_refund', 'in_receipt'):
                line.budget_type_filter = 'expense'
            else:
                line.budget_type_filter = False
