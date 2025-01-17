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
    actual_target = fields.Integer(string="Actual Targets Units",)
    workplan_state = fields.Selection(related='workplan_line_id.workplan_state', string='Workplan State', store=True, readonly=True)
    state = fields.Selection([
        ('draft','Draft'),
        ('inprogress', 'In-Progress'),
        ('submit', 'Submited'),
        ('done', 'Done')
        ], 'Status', default='inprogress', index=True, required=True, readonly=True, copy=False, tracking=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)
    unit_amount = fields.Monetary('Unit Estimate',)
    total_amount = fields.Monetary('Budget Estimate',compute="_compute_total_amount",)
    allocated_balance = fields.Monetary('Allocated Balance',compute="_compute_allocated_balance",)
    uom_id = fields.Many2one('uom.uom', 'Unit of Measure',)
    uom_name = fields.Char(string='Unit of Measure Name', related='uom_id.name', readonly=True)
    general_budget_id = fields.Many2one('account.budget.post', 'Budgetary Activity')

    @api.depends('unit_amount','planned_target')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = 0
            if record.planned_target and record.unit_amount:
                record.total_amount = record.planned_target * record.unit_amount

    
    def _compute_allocated_balance(self):
        for record in self:
            budget_line = self.env['crossovered.budget.lines'].search([('task_id','=',record.id)])
            if budget_line:
                record.allocated_balance = budget_line.allocated_balance