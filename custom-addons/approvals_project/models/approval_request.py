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


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    task_id = fields.Many2one(
        'project.task',
        string='Related Activity',
        ondelete='set null',readonly=True
    )

    allocated_balance = fields.Float(
        string='Allocated Balance',
        compute="_compute_allocated_balance",
        readonly=True,
    )

    def _compute_allocated_balance(self):
        for record in self:
            record.allocated_balance = 0
            budget_line = record.task_id._get_budget_line(record.task_id.id)
            if budget_line:
                record.allocated_balance = budget_line.allocated_balance

    def action_view_task(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Task',
            'res_model': 'project.task',
            'res_id': self.task_id.id,
            'view_mode': 'form',
            'target': 'current',
        }