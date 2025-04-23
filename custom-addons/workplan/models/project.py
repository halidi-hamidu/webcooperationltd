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


class ProjectTaskType(models.Model):
    _inherit = "project.task"

    workplan_activity = fields.Boolean(string="Activity from workplan", default=False,)
    workplan_line_id = fields.Many2one('workplan.workplan.lines', 'Objective',)
    planned_target = fields.Integer(string="Planned Target Units",tracking=True)
    actual_target = fields.Integer(string="Actual Targets Units", compute="_compute_actual_target_and_progress",  readonly=True)
    workplan_state = fields.Selection(related='workplan_line_id.workplan_state', string='Workplan State', store=True, readonly=True)
    workplan_task_state = fields.Selection([
        ('draft','Draft'),
        ('inprogress', 'In-Progress'),
        ('submit', 'Submited'),
        ('done', 'Done')
        ], 'Status', default='inprogress', index=True, required=True, copy=False, tracking=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    unit_amount = fields.Monetary('Unit Estimate',tracking=True)
    total_amount = fields.Monetary('Total Estimate',compute="_compute_total_amount",tracking=True)
    budget_amount = fields.Monetary('Budget Amount',compute="_compute_budget_amount")
    allocated_balance = fields.Monetary('Allocated Balance',compute="_compute_allocated_balance",)
    uom_id = fields.Many2one('uom.uom', 'Unit of Measure',)
    uom_name = fields.Char(string='Unit of Measure Name', related='uom_id.name', readonly=True)
    general_budget_id = fields.Many2one('account.budget.post', 'Budgetary Activity')
    weight = fields.Integer(string='Weight', default=0.0)
    child_tasks = fields.One2many('project.task', 'parent_id', string='Child Tasks')
    object_id = fields.Many2one(related='workplan_line_id.objective_id', string='Objective')
    outcome_id = fields.Many2one(related='workplan_line_id.outcome_id', string='Outcome')
    progress = fields.Float(string="Progress", default=0.0, compute="_compute_actual_target_and_progress")


    def get_name(self):
        self.ensure_one()
        if self.workplan_activity:
            return f"{self.object_id.name} - {self.outcome_id.name}"
        return super(ProjectTaskType, self).get_name()

    @api.depends('unit_amount','planned_target')
    def _compute_total_amount(self):
        for record in self:
            if record.planned_target and record.unit_amount:
                record.total_amount = record.planned_target * record.unit_amount
            else:
                record.total_amount = 0

    def _compute_budget_amount(self):
        for record in self:
            budget_line = self._get_budget_line(record.id)
            if budget_line:
                record.budget_amount = abs(budget_line.planned_amount)
            else:
                record.budget_amount = 0
    
    def _compute_allocated_balance(self):
        for record in self:
            record.allocated_balance = 0
            budget_line = self._get_budget_line(record.id)
            if budget_line:
                record.allocated_balance = budget_line.allocated_balance
    
    def _get_budget_line(self,task_id):
        budget_line = self.env['crossovered.budget.lines'].sudo().search([('task_id','=',task_id)])
        if budget_line:
            return budget_line
        else:
            return None

    @api.depends('planned_target', 'child_tasks.workplan_task_state', 'child_tasks.weight')
    def _compute_actual_target(self):
        for record in self:
            if record.id:
                total_weight = sum(task.weight for task in record.child_tasks if task.workplan_task_state == 'done')
                record.actual_target = (total_weight / 100) * record.planned_target
            else:
                # Set actual_target to 0 if there are no child tasks
                record.actual_target = 0

    @api.depends('planned_target', 'child_tasks.workplan_task_state', 'child_tasks.weight')
    def _compute_actual_target_and_progress(self):
        """
        Computes the actual target and progress for each record.
        """
        for record in self:
            if record.id:
                # Compute Actual Target
                total_weight = sum(task.weight for task in record.child_tasks if task.workplan_task_state == 'done')
                record.actual_target = (total_weight / 100) * record.planned_target if record.planned_target > 0 else 0

                # Compute Progress
                done_tasks = len(record.child_tasks.filtered(lambda task: task.workplan_task_state == 'done'))
                record.progress = (done_tasks / record.planned_target) * 100 if record.planned_target > 0 else 0.0
            else:
                record.actual_target = 0
                record.progress = 0.0