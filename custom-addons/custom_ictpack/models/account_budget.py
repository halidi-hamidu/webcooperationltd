# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import ustr
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning


# ---------------------------------------------------------
# Budgets
# ---------------------------------------------------------
class AccountBudgetPost(models.Model):
    _inherit = "account.budget.post"
    _sql_constraints = [('gfs_unique', 'unique(gfs_code,company_id',
                         'GFS Code should be unique for a Company')]

    gfs_code = fields.Char('GFS Code', required=True)

    activity_type = fields.Selection(
        selection=[('recurrent', 'Recurrent Expenditure'),
                   ('development', 'Development Expenditure')],
        string='Activity Type',
        default='recurrent',
    )

    def name_get(self):
        res = []
        for position in self:
            name = position.name
            if position.gfs_code:
                name = '[' + position.gfs_code + '] ' + name
            res.append((position.id, name))
        return res


class CrossoveredBudget(models.Model):
    _inherit = "crossovered.budget"

    type = fields.Selection(
        selection=[('expenditure', 'Expenditure Budget'),
                   ('revenue', 'Revenue Budget')],
        string='Budget Type',
        default='expenditure',
        required=True,
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting'),
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('validate', 'Validated'),
        ('done', 'Done')
    ], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, track_visibility='always')

    def action_budget_send(self):
        self.write({'state': 'waiting'})

    def action_budget_reset(self):
        self.write({'state': 'draft'})

    def unlink(self):
        if self.state not in ('draft', 'cancel'):
            raise UserError(
                _('Cannot delete Budget(s) which are already confirmed or done.'))
        else:
            return super(CrossoveredBudget, self).unlink()

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

    state = fields.Selection([
        ('draft', 'Draft'),
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('validate', 'Validated'),
        ('done', 'Done')
    ], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, track_visibility='always')
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.user.company_id)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency", readonly=True,
                                  default=lambda self: self.env.user.company_id.currency_id.id)
    voucher_budget_line = fields.One2many(
        'account.move.line', 'budget_line_id', 'Budget Lines')
    budget_line_allocation = fields.One2many(
        'account.budget.allocation', 'budget_line_id', 'Budget Lines')
    quantity = fields.Float(string='Quantity', digits=0, )
    unit_of_measure = fields.Many2one('uom.uom', 'Unit of Measures')
    unit_cost = fields.Float(string='Unit Cost', digits=0)
    allocated_amount = fields.Float(
        compute='_compute_allocated_amount', string='Allocated Amount', digits=0)
    budget_balance = fields.Float(
        compute='_compute_budget_balance', string='Budget Balance', digits=0)
    allocated_balance = fields.Float(compute='_compute_allocated_balance', string='Allocated Balance', digits=0,
                                     store=False)
    planned_amount = fields.Float('Budgeted Amount', required=True, digits=0, default=0, store=True,
                                  compute='_compute_planned')
    crossovered_budget_type = fields.Selection(
        related='crossovered_budget_id.type', string='Budget Type')

    @api.depends('quantity', 'unit_cost')
    @api.onchange('quantity', 'unit_cost')
    def _compute_planned(self):
        for budget in self:
            if budget.quantity or budget.unit_cost:
                budget.planned_amount = budget.unit_cost * budget.quantity
            else:
                budget.planned_amount = 0

    def name_get(self):
        res = []
        for position in self:
            name = position.general_budget_id.name
            if position.general_budget_id.gfs_code:
                name = '[' + position.general_budget_id.gfs_code + '] ' + name
            res.append((position.id, name))
        return res

    def _compute_allocated_amount(self):
        for line in self:
            line.allocated_amount = 0
            if line.id:
                date_to = self.env.context.get(
                    'wizard_date_to') or line.date_to
                date_from = self.env.context.get(
                    'wizard_date_from') or line.date_from
                budget_line_id = line.id
                if budget_line_id:
                    self.env.cr.execute("""
                                         SELECT SUM(amount)
                                          FROM account_budget_allocation
                                           WHERE budget_line_id=%s
                                            AND date between %s AND %s
                                                            """,
                                        (budget_line_id, date_from, date_to))
                line.allocated_amount = self.env.cr.fetchone()[0] or 0.0

    def _compute_budget_balance(self):
        for line in self:
            line.budget_balance = 0
            if line.id:
                result = (line.planned_amount - line.allocated_amount) or 0.0
                line.budget_balance = result

    def _compute_allocated_balance(self):
        for line in self:
            if line.id:
                result = (line.allocated_amount + line.practical_amount) or 0.0
                line.allocated_balance = result

    def open_budget_allocation_form(self):
        context = self.env.context
        view = self.env.ref('custom_ictpack.view_budget_allocation_form_button')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Allocation',
            'res_model': 'account.budget.allocation',
            'view_type': 'form',
            'view_id': view.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_analytic_line_id': context.get('analytic_line_id', False),
                        'default_currency_id': context.get('currency_id', False),
                        'default_is_relocation': False,
                        'default_general_budget_id': context.get('general_budget_id'),
                        'default_budget_line_id': context.get('budget_line_id', False),
                        'default_date_from': context.get('date_from', False),
                        'default_date_to': context.get('date_to', False)},
        }


class AccountBudgetAllocation(models.Model):
    _name = "account.budget.allocation"
    _description = 'Budget Allocation'
    _order = 'date desc, id desc'

    @api.model
    def _default_user(self):
        return self.env.context.get('user_id', self.env.user.id)

    name = fields.Char('Description', required=True)
    date = fields.Date('Date', required=True, index=True,
                       default=fields.Date.context_today)
    date_from = fields.Date('Start Date', required=True)
    date_to = fields.Date('End Date', required=True)
    amount = fields.Monetary('Amount', required=True, default=0.0)
    user_id = fields.Many2one(
        'res.users', string='User', default=_default_user)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.user.company_id)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency", readonly=True,
                                  default=lambda self: self.env.user.company_id.currency_id.id)
    budget_line_id = fields.Many2one('crossovered.budget.lines', 'Activity')
    analytic_line_id = fields.Many2one('account.analytic.account', 'Objective',
                                       related='budget_line_id.analytic_account_id', readonly=True, store=True, )
    general_budget_id = fields.Many2one('account.budget.post', 'Activity', related='budget_line_id.general_budget_id',
                                        readonly=True, store=True)
    # available_balance = fields.Float('Available Balance', digits=0, default=0, readonly=True,
    #                                  compute='_compute_available_balance')
    # balance = fields.Float('Balance', digits=0, default=0, compute='_cumpute_balance')
    is_relocation = fields.Boolean('Relocation entry', default=False, )

    @api.model
    def create(self, values):
        context = self.env.context
        analytic_line_id = context.get('analytic_line_id', False)
        budget_line_id = context.get('budget_line_id', False)
        if not analytic_line_id:
            analytic_line_id = values['analytic_line_id']
        if not budget_line_id:
            budget_line_id = values['budget_line_id']
        analytic_balance = self._compute_analytic_balance(
            values['date_from'], values['date_to'], analytic_line_id)
        allocation_balance = self._compute_allocated_balance(
            values['date_from'], values['date_to'], analytic_line_id)
        balance = analytic_balance - allocation_balance
        budget_obj = self.env['crossovered.budget.lines'].browse(
            budget_line_id)

        if budget_obj:
            total = budget_obj.allocated_amount + values['amount']
            if total > budget_obj.planned_amount:
                raise Warning(
                    _("You can not Allocate more that Budgted Amount"))
            elif values['is_relocation']:
                record = super(AccountBudgetAllocation, self).create(values)
                return record
            else:
                if (values['amount'] <= balance and values['amount'] != 0):
                    record = super(AccountBudgetAllocation,
                                   self).create(values)
                    return record
                elif values['amount'] >= balance and values['amount'] > 0:
                    raise Warning(
                        _("You can not Allocate more that available balance (%f)" % balance))
                elif values['amount'] == 0:
                    raise Warning(_("You can not Allocate Zero Amount!"))
                # return record
        else:
            raise Warning(_("No budget line selected!"))

    def create_allocation(self):
        if self.id:
            return {'type': 'ir.actions.act_window_close'}
        else:
            return False

    def _compute_available_balance(self):
        context = self.env.context
        analytic_balance = self._compute_analytic_balance(context.get('date_from', False),
                                                          context.get(
                                                              'date_to', False),
                                                          context.get('analytic_line_id', False))
        allocation_balance = self._compute_allocated_balance(context.get('date_from', False),
                                                             context.get(
                                                                 'date_to', False),
                                                             context.get('analytic_line_id', False))
        balance = analytic_balance - allocation_balance
        return balance

    def _compute_allocated_balance(self, date_from, date_to, analytic_line_id):
        analytic_account = self.env['account.analytic.account'].browse(
            analytic_line_id)
        self.env.cr.execute("""
                             SELECT SUM(amount)
                                    FROM account_budget_allocation
                                    WHERE analytic_line_id=%s
                                        AND date between %s AND %s
                                        AND amount >= 0""",
                            (analytic_account.id, date_from, date_to))

        credit_allocation = self.env.cr.fetchone()[0] or 0.0
        self.env.cr.execute("""
                                     SELECT SUM(amount)
                                            FROM account_budget_allocation
                                            WHERE analytic_line_id=%s
                                                AND date between %s AND %s
                                                AND amount < 0""",
                            (analytic_account.id, date_from, date_to))
        debit_allocation = self.env.cr.fetchone()[0] or 0.0
        return credit_allocation + debit_allocation

    def _compute_analytic_balance(self, date_from, date_to, analytic_line_id):
        analytic_account = self.env['account.analytic.account'].browse(
            analytic_line_id)
        self.env.cr.execute("""
                            SELECT SUM(amount)
                            FROM account_analytic_line
                            WHERE account_id=%s
                                AND date between %s AND %s
                                AND amount >= 0""",
                            (analytic_account.id, date_from, date_to))
        result = self.env.cr.fetchone()[0] or 0.0
        return result

    @api.onchange('amount')
    def _compute_planned(self):
        for allocation in self:
            res = {}
            if allocation.amount < 0:
                res['warning'] = {'title': 'Negative Allocation',
                                  'message': '''Allocated Amount Can not be Negative'''}
                res['value'] = {'amount': abs(allocation.amount)}
                return res


class AccountBudgetRelocation(models.Model):
    _name = "account.budget.relocation"
    _description = 'Budget Relocation'
    _order = 'date desc, id desc'

    @api.model
    def _default_user(self):
        return self.env.context.get('user_id', self.env.user.id)

    name = fields.Char('Description', required=True)
    date = fields.Date('Date', required=True, index=True, default=fields.Date.context_today,
                       states={'approved': [('readonly', True)]})
    user_id = fields.Many2one(
        'res.users', string='Started By', default=_default_user)
    approved_by = fields.Many2one('res.users', string='Approved By')
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.user.company_id)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency", readonly=True,
                                  default=lambda self: self.env.user.company_id.currency_id.id)
    amount = fields.Monetary('Amount', required=True, default=0.0, states={
                             'approved': [('readonly', True)]})
    from_budget_line_id = fields.Many2one('crossovered.budget.lines', 'Source Budget Line', required=True,
                                          states={'approved': [('readonly', True)]})
    to_budget_line_id = fields.Many2one('crossovered.budget.lines', 'Destination Budget Line', required=True,
                                        states={'approved': [('readonly', True)]})
    status = fields.Selection(
        string='State', related='from_budget_line_id.state')
    available_amount = fields.Monetary(
        'Available amount', default=0.0, readonly=True, store=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting', 'Waiting Approval'),
        ('cancel', 'Cancelled'),
        ('approved', 'Approved'),
        ('relocated', 'Relocated'),
    ], 'Status', readonly=True, track_visibility='onchange', copy=False, default='draft',
        help=" * The 'Draft' status is used when a user is encoding a new and unconfirmed Relocation.\n"
             " * The 'Approved' status is used when the relocation has been approved.\n"
             " * The 'relocated' status is used when relocation of fund is complete.\n"
             " * The 'Cancelled' status is used when user cancel relocation.")

    @api.onchange('from_budget_line_id')
    def budget_line_id_change(self):
        from_budget_line = self.env['crossovered.budget.lines'].browse(
            self.from_budget_line_id.id)
        setattr(self, 'available_amount', from_budget_line.allocated_balance)

    def draft_relocation(self):
        if self.amount <= self.from_budget_line_id.allocated_balance:
            self.write({'state': 'waiting'})
        else:
            raise Warning(
                _("Relocation amount is greater than amount available!"))

    def approve_relocation(self):
        if self.from_budget_line_id.id != self.to_budget_line_id.id and self.amount > 0:
            self.write({'approved_by': self._uid, 'state': 'approved'})
        else:
            raise Warning(
                _("Two budget Lines must be different and amount to relocate must be positive"))

    def cancel_relocation(self):
        self.write({'state': 'cancel'})

    def action_cancel_draft(self):
        self.write({'state': 'draft'})

    def unlink(self):
        for voucher in self:
            if voucher.state not in ('draft', 'cancel'):
                raise UserError(
                    _('Cannot delete realocation(s) which are already completed!'))
        return super(AccountBudgetRelocation, self).unlink()

    def complete_relocation(self):
        from_budget_line = self.env['crossovered.budget.lines'].browse(
            self.from_budget_line_id.id)
        to_budget_line = self.env['crossovered.budget.lines'].browse(
            self.to_budget_line_id.id)
        if self.amount <= from_budget_line.allocated_balance:
            debit_line = {
                'name': self.name,
                # 'date': fields.Date.context_today,
                'date_from': from_budget_line.date_from,
                'date_to': from_budget_line.date_to,
                'amount': -self.amount,
                'user_id': self._uid,
                'company_id': from_budget_line.company_id.id,
                'budget_line_id': from_budget_line.id,
                'analytic_line_id': from_budget_line.analytic_account_id.id,
                'is_relocation': True,
            }

            debit_line_analytic = {
                'name': 'Relocation to another Budget Line',
                'date': self.date,
                'amount': -self.amount,
                'user_id': self.create_uid.id,
                'company_id': from_budget_line.company_id.id,
                'currency_id': 138,
                'account_id': from_budget_line.analytic_account_id.id,
            }

            credit_line = {
                'name': self.name,
                # 'date': fields.Date.context_today,
                'date_from': to_budget_line.date_from,
                'date_to': to_budget_line.date_to,
                'amount': self.amount,
                'user_id': self._uid,
                'company_id': to_budget_line.company_id.id,
                'budget_line_id': to_budget_line.id,
                'analytic_line_id': to_budget_line.analytic_account_id.id,
                'is_relocation': True,
            }

            credit_line_analytic = {
                'name': 'Allocation to another budget line',
                'date': self.date,
                'amount': self.amount,
                'user_id': self.create_uid.id,
                'company_id': 1,
                'currency_id': 138,
                'account_id': to_budget_line.analytic_account_id.id,
            }
            self.env['account.budget.allocation'].create(debit_line)
            self.env['account.budget.allocation'].create(credit_line)
            self.env['account.analytic.line'].create(debit_line_analytic)
            self.env['account.analytic.line'].create(credit_line_analytic)
            self.write({'state': 'relocated'})
        else:
            raise Warning(
                _("You can not Allocate more that available balance!"))

    def action_correct_relocation(self):
        relocations = self.env['account.budget.relocation'].search(
            [('state', '=', 'relocated')])
        for relocation in relocations:
            debit_line = {
                'name': 'Relocation to another Budget Line',
                'date': relocation.date,
                'amount': -relocation.amount,
                'user_id': relocation.create_uid.id,
                'company_id': 1,
                'currency_id': 138,
                'account_id': relocation.from_budget_line_id.analytic_account_id.id,
            }

            credit_line = {
                'name': 'Allocation to another budget line',
                'date': relocation.date,
                'amount': relocation.amount,
                'user_id': relocation.create_uid.id,
                'company_id': 1,
                'currency_id': 138,
                'account_id': relocation.to_budget_line_id.analytic_account_id.id,
            }
            self.env['account.analytic.line'].create(debit_line)
            self.env['account.analytic.line'].create(credit_line)
