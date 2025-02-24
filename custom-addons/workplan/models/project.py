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
    planned_target = fields.Integer(string="Planned Target Units", )
    actual_target = fields.Integer(string="Actual Targets Units", compute="_compute_actual_target", store=True)
    workplan_state = fields.Selection(related='workplan_line_id.workplan_state', string='Workplan State', store=True, readonly=True)
    workplan_task_state = fields.Selection([
        ('draft','Draft'),
        ('inprogress', 'In-Progress'),
        ('submit', 'Submited'),
        ('done', 'Done')
        ], 'Status', default='inprogress', index=True, required=True, copy=False, tracking=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    unit_amount = fields.Monetary('Unit Estimate',)
    total_amount = fields.Monetary('Budget Estimate',compute="_compute_total_amount",)
    allocated_balance = fields.Monetary('Allocated Balance',compute="_compute_allocated_balance",)
    uom_id = fields.Many2one('uom.uom', 'Unit of Measure',)
    uom_name = fields.Char(string='Unit of Measure Name', related='uom_id.name', readonly=True)
    general_budget_id = fields.Many2one('account.budget.post', 'Budgetary Activity')
    weight = fields.Integer(string='Weight', default=0.0)

    is_uom_id_readonly = fields.Boolean(string='Is UOM ID Readonly', compute='_compute_is_field_readonly')
    is_planned_target_readonly = fields.Boolean(string='Is Planned Target Readonly', compute='_compute_is_field_readonly')
    child_tasks = fields.One2many('project.task', 'parent_id', string='Child Tasks')
    object_id = fields.Many2one(related='workplan_line_id.objective_id', string='Objective')
    outcome_id = fields.Many2one(related='workplan_line_id.outcome_id', string='Outcome')

    def get_name(self):
        self.ensure_one()
        if self.workplan_activity:
            return f"{self.object_id.name} - {self.outcome_id.name}"
        return super(ProjectTaskType, self).get_name()

    @api.depends('uom_id', 'planned_target')
    def _compute_is_field_readonly(self):
        field_names = ['uom_id', 'planned_target']
        for record in self:
            for field_name in field_names:
                config = self.env['project.task.config'].sudo().search([('field_name', '=', field_name)], limit=1)
                readonly = config.readonly if config else False
                setattr(record, f'is_{field_name}_readonly', readonly)

    @api.depends('unit_amount','planned_target')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = 0
            if record.planned_target and record.unit_amount:
                record.total_amount = record.planned_target * record.unit_amount

    
    def _compute_allocated_balance(self):
        for record in self:
            record.allocated_balance = 0
            budget_line = self.env['crossovered.budget.lines'].search([('task_id','=',record.id)])
            if budget_line:
                record.allocated_balance = budget_line.allocated_balance

    @api.depends('planned_target', 'child_tasks.workplan_task_state', 'child_tasks.weight')
    def _compute_actual_target(self):
        for record in self:
            if record.id:
                total_weight = sum(task.weight for task in record.child_tasks if task.workplan_task_state == 'done')
                record.actual_target = (total_weight / 100) * record.planned_target
            else:
                record.actual_target = 0

    def action_open_workplan_activity(self, domain=None,context=None):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f"{self.object_id.name} - {self.outcome_id.name}",
            'res_model': 'project.task',
            'view_mode': 'tree,form,calendar,kanban,pivot,graph,activity',
            'domain': domain,
            'context': {'search_default_open_tasks': 1, 'all_task': 1} + context,
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

class ProjectTaskConfig(models.Model):
    _name = 'project.task.config'
    _description = 'Project Task Configuration'

    name = fields.Char(string='Name', required=True)
    field_name = fields.Char(string='Field Name', required=True)
    readonly = fields.Boolean(string='Readonly', default=True)