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
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import ast

class WorkplanWorkplan(models.Model):
    _name = "workplan.workplan"
    _description = "Workplan"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Workplan Name', required=True, states={'done': [('readonly', True)]})
    user_id = fields.Many2one('res.users', 'Responsible', default=lambda self: self.env.user)
    department_id = fields.Many2one('hr.department', 'Department', compute="_compute_department_project", store=True)
    project_id = fields.Many2one('project.project', 'Operational Project', compute="_compute_department_project", store=True)
    date_from = fields.Date('Start Date', states={'done': [('readonly', True)]})
    date_to = fields.Date('End Date', states={'done': [('readonly', True)]})
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submited'),
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('validate', 'Validated'),
        ('done', 'Done')
        ], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    workplan_lines = fields.One2many('workplan.workplan.lines', 'workplan_id', 'Workplan Lines', states={'done': [('readonly', True)]}, copy=True)
    
    @api.depends('user_id')
    def _compute_department_project(self):
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        if employee:
            self.department_id = employee.department_id.id
            self.project_id = employee.department_id.project_id.id


    def action_workplan_submit(self):
        self.write({'state': 'submit'})

    def action_workplan_confirm(self):
        ## Create budget lines from activities
        budget =  self.env['crossovered.budget'].search([('type','=','expenditure'),('state','=','draft'),
                                                         ('date_from','>=',self.date_from),('date_to','<=',self.date_to)],limit=1)
        if budget:
            for line in self.workplan_lines:
                for task in line.task_ids:
                    if task.general_budget_id and task.total_amount > 0:
                        budget.write({
                            'crossovered_budget_line': [(0,0,{'general_budget_id':task.general_budget_id.id,
                                                              'date_from':self.date_from,'date_to':self.date_to,
                                                              'analytic_account_id':task.analytic_account_id.id,'task_id':task.id,
                                                              'planned_amount': - task.total_amount})]
                        })
            self.write({'state': 'confirm'})
        else:
            raise ValidationError(_('There is No DRAFT Expenditure Budget to associate with Workplan'))

    def action_workplan_draft(self):
        self.write({'state': 'draft'})

    def action_workplan_validate(self):
        self.write({'state': 'validate'})

    def action_workplan_cancel(self):
        ## Cancel budget lines from activities
        budget =  self.env['crossovered.budget'].search([('type','=','expenditure'),('state','=','draft'),
                                                         ('date_from','>=',self.date_from),('date_to','<=',self.date_to)],limit=1)
        if budget:
            for line in self.workplan_lines:
                for task in line.task_ids:
                    budget_lines = self.env['crossovered.budget.lines'].search([('task_id','=',task.id)])
                    for budget_line in budget_lines:
                        budget_line.unlink()
            self.write({'state': 'cancel'})
        else:
            raise ValidationError(_('Expenditure Budget is not in Draft State!'))
        

    def action_workplan_done(self):
        self.write({'state': 'done'})
    


class WorkplanWorkplanLines(models.Model):
    _name = "workplan.workplan.lines"
    _description = "Workplan Line"

    #name = fields.Char(compute='_compute_line_name')
    workplan_id = fields.Many2one('workplan.workplan', 'Workplan', ondelete='cascade', index=True, required=True)
    objective_id = fields.Many2one('workplan.objective', 'Objective',required=True)
    outcome_id = fields.Many2one('workplan.outcome', 'Outcome',domain="[('objective_id', '=?', objective_id)]",required=True)
    indicator_id = fields.Many2one('workplan.indicator', 'Indicator',domain="[('outcome_id', '=?', outcome_id)]",required=True)
    department_id = fields.Many2one(related='workplan_id.department_id', string='Department', store=True)
    measure = fields.Char(related='indicator_id.measure', string='Measure', store=True, readonly=True)
    target = fields.Float(string="Goal", default=0.0)
    date_from = fields.Date('Start Date', required=True)
    date_to = fields.Date('End Date', required=True)
    company_id = fields.Many2one(related='workplan_id.company_id', string='Company', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    workplan_state = fields.Selection(related='workplan_id.state', string='Workplan State', store=True, readonly=True)
    project_id = fields.Many2one('project.project', 'Operational Project', related='workplan_id.project_id')
    planned_target = fields.Integer(string="Planned Targets",compute="_compute_planned_actual_balance",readonly=True)
    actual_target = fields.Integer(string="Actual Targets", compute="_compute_planned_actual_balance",readonly=True)
    task_ids = fields.One2many('project.task', 'workplan_line_id', 'Activities', states={'done': [('readonly', True)]}, copy=True)
    progress = fields.Float(string="Progress", default=0.0, compute="_compute_planned_actual_balance")
    budget_estimate = fields.Monetary('Budget Estimate',compute="_compute_planned_actual_balance",)
    allocated_balance = fields.Monetary('Allocated Balance',compute="_compute_planned_actual_balance",)

    #Add unique constraint for the three fields
    _sql_constraints = [
        (
            'unique_objective_outcome_indicator',
            'UNIQUE (objective_id, outcome_id, indicator_id,department_id)',
            'The combination of Objective, Outcome, and Indicator must be unique!'
        ),
    ]
    
    @api.depends('task_ids.planned_target','task_ids.actual_target')
    def _compute_planned_actual_balance(self):
        for line in self:
            planned = 0
            actual = 0
            allocated = 0
            estimate = 0
            for task in line.task_ids:
                planned += task.planned_target
                actual += task.actual_target
                estimate += task.total_amount
                allocated += task.allocated_balance
            line.planned_target = planned
            line.actual_target = actual
            line.budget_estimate = estimate
            line.allocated_balance = allocated
            if planned != 0:
                line.progress = (actual / planned) * 100
            else:
                line.progress = 0.0


    @api.onchange('workplan_id')
    def _onchange_workplan_id(self):
        if self.workplan_id:
            self.date_from = self.date_from or self.workplan_id.date_from
            self.date_to = self.date_to or self.workplan_id.date_to

    @api.constrains('date_from', 'date_to')
    def _line_dates_between_workplan_dates(self):
        for line in self:
            workplan_date_from = line. workplan_id.date_from
            workplan_date_to = line. workplan_id.date_to
            if line.date_from:
                date_from = line.date_from
                if (workplan_date_from and date_from < workplan_date_from) or (workplan_date_to and date_from > workplan_date_to):
                    raise ValidationError(_('"Start Date" of the workplan line should be included in the Period of the workplan'))
            if line.date_to:
                date_to = line.date_to
                if (workplan_date_from and date_to < workplan_date_from) or (workplan_date_to and date_to > workplan_date_to):
                    raise ValidationError(_('"End Date" of the workplan line should be included in the Period of the workplan'))
    
    def action_view_activities(self):
        self.ensure_one()
        domain = [('workplan_line_id', '=', self.id), ('workplan_activity', '=', True)]
        context = {
                'default_project_id': self.project_id.id,
                'default_workplan_line_id': self.id,
                'default_workplan_activity': True,
                'search_default_open_tasks': 1,
                'all_task': 1,
             }
        return {
            'type': 'ir.actions.act_window',
            'name': f"{self.objective_id.name} - {self.outcome_id.name}",
            'res_model': 'project.task',
            'view_mode': 'tree,form,calendar,kanban,pivot,graph,activity',
            'domain': domain,
            'context': context,
            'search_view_id': self.env.ref('project.view_task_search_form_extended').id,
            'help': """
                <p class="o_view_nocontent_smiling_face">
                    No tasks found. Let's create one!
                </p>
                <p>
                    Organize your tasks by dispatching them across the pipeline.<br/>
                    Collaborate efficiently by chatting in real-time or via email.
                </p>
            """,
        }