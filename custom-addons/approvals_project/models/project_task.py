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


class ProjectTask(models.Model):
    _inherit = 'project.task'

    approval_request_ids = fields.One2many(
        'approval.request', 
        'task_id', 
        string='Approval Requests'
    )

    approval_request_count = fields.Integer(
        compute='_compute_approval_request_count',
        string='Approval Count'
    )

    def _compute_approval_request_count(self):
        for task in self:
            task.approval_request_count = len(task.approval_request_ids)

    def action_create_approval_request(self):
        self.ensure_one()
        self.message_post(
            body=f"{self.env.user.name} has requested fund approval for this Activity",
            message_type='comment',  # Internal Note
            subtype_xmlid='mail.mt_note',  # Internal note subtype
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Approval Request',
            'res_model': 'approval.request',
            'view_mode': 'form',
            'context': {
                'default_task_id': self.id,
                'default_name': f'New',
                'default_request_owner_id': self.env.user.id,
                'default_reason': self.name,
            },
            'target': 'current',
        }
    
    def action_view_approval_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Approval Requests',
            'res_model': 'approval.request',
            'view_mode': 'tree,form',
            'domain': [('task_id', '=', self.id)],
            'context': {
                'default_task_id': self.id,
                'create': False
            }
        }