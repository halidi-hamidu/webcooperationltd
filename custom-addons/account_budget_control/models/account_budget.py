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
from collections import defaultdict


# ---------------------------------------------------------
# Budgets
# ---------------------------------------------------------
class CrossoveredBudget(models.Model):
    _inherit = "crossovered.budget"

    type = fields.Selection(
        selection=[('expenditure', 'Expenditure Budget'),
                   ('project', 'Project Budget'),
                   ('revenue', 'Revenue Budget')],
        string='Budget Type',
        default='project',
        required=True, states={'done': [('readonly', True)]}
    )

    def action_budget_validate(self):
        budget = self.env['crossovered.budget'].search(
            [('state', '=', 'validate'), ('type', '=', self.type)])
        if budget:
            raise UserError(_(
                'Cannot have more than one Budget in validated state.'
                ' Please complete circle of previous budget to done before validating a new one'))
        else:
            return super(CrossoveredBudget, self).action_budget_validate()
    
    
class CrossoveredBudgetLines(models.Model):
    _inherit = "crossovered.budget.lines"

    budget_balance = fields.Monetary(compute='_compute_budget_balance', string='Budget Balance')
    allocated_amount = fields.Monetary(compute='_compute_allocated_amount', string='Allocated Amount')
    allocated_balance = fields.Monetary(compute='_compute_allocated_amount', string='Allocated Balance')
    crossovered_budget_type = fields.Selection(related='crossovered_budget_id.type', string='Budget Type')
    allocation_lines = fields.One2many('account.budget.allocation', 'budget_line_id', 'Allocation Lines')

    @api.depends('planned_amount','allocated_amount')
    def _compute_budget_balance(self):
        for line in self:
            line.budget_balance = (abs(line.planned_amount) - abs(line.allocated_amount)) or 0.0


    @api.depends('allocation_lines.amount','practical_amount')
    def _compute_allocated_amount(self):
        for line in self:
                allocated_amount = 0.0
                for allocation in line.allocation_lines:
                    allocated_amount += allocation.amount
                line.allocated_amount = allocated_amount
                line.allocated_balance = line.allocated_amount - abs(line.practical_amount)
                     

    def open_budget_allocation_form(self):
        context = self.env.context
        view = self.env.ref('account_budget_control.view_budget_allocation_form_button')
        allocation_type = context.get('is_relocation', False)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Relocation' if allocation_type else 'Allocation',
            'res_model': 'account.budget.allocation',
            'view_type': 'form',
            'view_id': view.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_analytic_line_id': context.get('analytic_line_id', False),
                        'default_is_relocation': context.get('is_relocation', False),
                        'default_general_budget_id': context.get('general_budget_id'),
                        'default_budget_line_id': context.get('budget_line_id', False)},
        }
    
    def _compute_practical_amount(self):
        def get_accounts(line):
            if line.analytic_account_id:
                return 'account.analytic.line', set(line.analytic_account_id.ids), line.id
            return 'account.move.line', set(line.general_budget_id.account_ids.ids), line.id

        def get_query(model, date_from, date_to, account_ids, line_id):
            domain = [
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('account_id', 'in', list(account_ids)),
            ]
            if model == 'account.move.line':
                domain += [
                    ('parent_state', '=', 'posted'),
                    ('budget_line_id', '=', line_id),  
                ]
                fname = '-balance'
                general_account = 'account_id'
            else:
                domain += [
                    ('crossovered_budget_line', '=', line_id),
                ]
                fname = 'amount'
                general_account = 'general_account_id'

            query = self.env[model]._search(domain)
            query.order = None
            query_str, params = query.select(
                '%s', '%s', '%s','%s', 'account_id', general_account, f'SUM({fname})'
            )
            params = [model, date_from, date_to, line_id] + params
            query_str += f" GROUP BY account_id, {general_account}"
            return query_str, params

        # Group by (model, date_from, date_to, line_id)
        groups = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
        for line in self:
            model, accounts, line_id = get_accounts(line)
            groups[model][(line.date_from, line.date_to)][line_id].update(accounts)

        queries = []
        queries_params = []
        for model, by_date in groups.items():
            for (date_from, date_to), by_line in by_date.items():
                for line_id, account_ids in by_line.items():
                    if account_ids:
                        query, params = get_query(model, date_from, date_to, account_ids, line_id)
                        queries.append(query)
                        queries_params += params

        if not queries:
            self.practical_amount = 0
            return

        self.env.cr.execute(" UNION ALL ".join(queries), queries_params)

        # New aggregation: {(model, date_from, date_to, line_id): {account_id: amount}}
        agg_per_line = defaultdict(lambda: defaultdict(float))
        for model, date_from, date_to, line_id, account_id, general_account_id, amount in self.env.cr.fetchall():
            agg_per_line[(model, date_from, date_to, line_id)][account_id] += amount

        for line in self:
            model, accounts, line_id = get_accounts(line)
            line.practical_amount = sum(
                agg_per_line.get((model, line.date_from, line.date_to, line_id), {}).get(account, 0)
                for account in accounts
            )



class AccountBudgetAllocation(models.Model):
    _name = "account.budget.allocation"
    _description = 'Budget Allocation/Relocation'
    _order = 'date desc, id desc'

    name = fields.Char('Description', required=True)
    date = fields.Date('Date', required=True, index=True, default=fields.Date.context_today)
    budget_line_id = fields.Many2one('crossovered.budget.lines', 'Budget Line',required=True)
    crossovered_budget_id = fields.Many2one('crossovered.budget', related='budget_line_id.crossovered_budget_id', store=True)
    date_from = fields.Date('Start Date',related="budget_line_id.date_from")
    date_to = fields.Date('End Date',related="budget_line_id.date_to")
    amount = fields.Monetary('Amount', required=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    company_id = fields.Many2one(related='budget_line_id.company_id', comodel_name='res.company',
        string='Company', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    analytic_line_id = fields.Many2one('account.analytic.account', 'Analytic',
                                       related='budget_line_id.analytic_account_id', readonly=True, store=True, )
    general_budget_id = fields.Many2one('account.budget.post', 'Budgetary Activity', related='budget_line_id.general_budget_id',
                                        readonly=True, store=True)
    is_relocation = fields.Boolean('Relocation entry', default=False)
    to_budget_line_id = fields.Many2one('crossovered.budget.lines', 'Destinaton Budget Line',
                                        domain="[('crossovered_budget_state','=','validate'),('crossovered_budget_id','=?',crossovered_budget_id)]")
    to_analytic_line_id = fields.Many2one('account.analytic.account', 'Destination Analytic', related='to_budget_line_id.analytic_account_id', readonly=True, store=True,)
    to_general_budget_id = fields.Many2one('account.budget.post', 'Destination Budgetary Activity', related='to_budget_line_id.general_budget_id',readonly=True, store=True)

    @api.model
    def create(self, values):
        context = self.env.context
        is_relocation = context.get('is_relocation', False)
        
        if is_relocation:
            from_budget_line_id = context.get('budget_line_id', False)
            to_budget_line_id = values['to_budget_line_id']
            from_budget_line = self.env['crossovered.budget.lines'].browse(from_budget_line_id)
            if from_budget_line.allocated_balance >= values['amount']:
                ###### for credit move
                values['budget_line_id'] = to_budget_line_id
                values['to_budget_line_id'] =  False
                record =  super(AccountBudgetAllocation,self).create(values)
                ###### for credit move
                values['budget_line_id'] = from_budget_line_id
                values['to_budget_line_id'] =  to_budget_line_id
                values['amount'] =  - values['amount']
                record =  super(AccountBudgetAllocation,self).create(values)
                return record
            else:
                raise ValidationError(_("You can not Relocate more that Allocated Balance"))
        else:
            budget_line_id = context.get('budget_line_id', False)
            if not budget_line_id:
                budget_line_id = values['budget_line_id']
            budget_line = self.env['crossovered.budget.lines'].browse(budget_line_id)

            if budget_line:
                if values['amount'] > budget_line.budget_balance:
                    raise ValidationError(_("You can not Allocate more that Budgted Amount"))
                else:
                    return super(AccountBudgetAllocation,self).create(values)
            else:
                raise ValidationError(_("No budget line selected!"))

    def create_allocation(self):
        if self.id:
            return {'type': 'ir.actions.act_window_close'}
        else:
            return False