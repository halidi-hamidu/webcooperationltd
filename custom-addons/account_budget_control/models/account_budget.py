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


# ---------------------------------------------------------
# Budgets (v19: budget.analytic replaces crossovered.budget)
# ---------------------------------------------------------
class BudgetAnalytic(models.Model):
    _inherit = "budget.analytic"

    budget_type = fields.Selection(selection_add=[('project', 'Project Budget')], ondelete={'project': 'cascade'})

    def action_budget_confirm(self):
        budget = self.env['budget.analytic'].search(
            [('state', '=', 'confirmed'), ('budget_type', '=', self.budget_type)])
        if budget:
            raise UserError(_(
                'Cannot have more than one Budget in confirmed state.'
                ' Please complete circle of previous budget to done before confirming a new one'))
        else:
            return super().action_budget_confirm()


# ---------------------------------------------------------
# Budget Lines (v19: budget.line replaces crossovered.budget.lines)
# ---------------------------------------------------------
class BudgetLine(models.Model):
    _inherit = "budget.line"

    budget_balance = fields.Monetary(compute='_compute_budget_balance', string='Budget Balance')
    allocated_amount = fields.Monetary(compute='_compute_allocated_amount', string='Allocated Amount')
    allocated_balance = fields.Monetary(compute='_compute_allocated_amount', string='Allocated Balance')
    budget_analytic_type = fields.Selection(related='budget_analytic_id.budget_type', string='Budget Type')
    allocation_lines = fields.One2many('account.budget.allocation', 'budget_line_id', 'Allocation Lines')

    @api.depends('budget_amount', 'allocated_amount')
    def _compute_budget_balance(self):
        for line in self:
            line.budget_balance = (abs(line.budget_amount) - abs(line.allocated_amount)) or 0.0

    @api.depends('allocation_lines.amount', 'achieved_amount')
    def _compute_allocated_amount(self):
        for line in self:
            allocated_amount = 0.0
            for allocation in line.allocation_lines:
                allocated_amount += allocation.amount
            line.allocated_amount = allocated_amount
            line.allocated_balance = line.allocated_amount - abs(line.achieved_amount)

    def open_budget_allocation_form(self):
        context = self.env.context
        view = self.env.ref('account_budget_control.view_budget_allocation_form_button')
        allocation_type = context.get('is_relocation', False)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Relocation' if allocation_type else 'Allocation',
            'res_model': 'account.budget.allocation',
            'view_id': view.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_is_relocation': context.get('is_relocation', False),
                'default_budget_line_id': context.get('budget_line_id', False),
            },
        }


class AccountBudgetAllocation(models.Model):
    _name = "account.budget.allocation"
    _description = 'Budget Allocation/Relocation'
    _order = 'date desc, id desc'

    name = fields.Char('Description', required=True)
    date = fields.Date('Date', required=True, index=True, default=fields.Date.context_today)
    budget_line_id = fields.Many2one('budget.line', 'Budget Line', required=True)
    budget_analytic_id = fields.Many2one('budget.analytic', related='budget_line_id.budget_analytic_id', store=True)
    date_from = fields.Date('Start Date', related="budget_line_id.date_from")
    date_to = fields.Date('End Date', related="budget_line_id.date_to")
    amount = fields.Monetary('Amount', required=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    company_id = fields.Many2one(
        related='budget_line_id.company_id', comodel_name='res.company',
        string='Company', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    is_relocation = fields.Boolean('Relocation entry', default=False)
    to_budget_line_id = fields.Many2one(
        'budget.line', 'Destination Budget Line',
        domain="[('budget_analytic_state', '=', 'confirmed'), ('budget_analytic_id', '=?', budget_analytic_id)]")

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            context = self.env.context
            is_relocation = context.get('is_relocation', False)

            if is_relocation:
                from_budget_line_id = context.get('budget_line_id', False)
                to_budget_line_id = values['to_budget_line_id']
                from_budget_line = self.env['budget.line'].browse(from_budget_line_id)
                if from_budget_line.allocated_balance >= values['amount']:
                    ###### for credit move
                    values['budget_line_id'] = to_budget_line_id
                    values['to_budget_line_id'] = False
                    record = super().create(values)
                    ###### for debit move
                    values['budget_line_id'] = from_budget_line_id
                    values['to_budget_line_id'] = to_budget_line_id
                    values['amount'] = -values['amount']
                    record = super().create(values)
                    return record
                else:
                    raise ValidationError(_("You can not Relocate more than Allocated Balance"))
            else:
                budget_line_id = context.get('budget_line_id', False)
                if not budget_line_id:
                    budget_line_id = values['budget_line_id']
                budget_line = self.env['budget.line'].browse(budget_line_id)

                if budget_line:
                    if values['amount'] > budget_line.budget_balance:
                        raise ValidationError(_("You can not Allocate more than Budgeted Amount"))
                    else:
                        return super().create(values)
                else:
                    raise ValidationError(_("No budget line selected!"))

    def create_allocation(self):
        if self.id:
            return {'type': 'ir.actions.act_window_close'}
        else:
            return False