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


class ResPartner(models.Model):
    _inherit = 'res.partner'

    project_ids = fields.One2many('project.project', 'partner_id', string='Projects')
    project_count = fields.Integer("Projects", compute='_compute_project_count',store=True)

    @api.depends('project_ids')
    def _compute_project_count(self):
        # retrieve all children partners and prefetch 'parent_id' on them
        all_partners = self.with_context(active_test=False).search([('id', 'child_of', self.ids)])
        all_partners.read(['parent_id'])

        # group sms by partner, and account for each partner in self
        groups = self.env['project.project'].read_group(
            [('partner_id', 'in', all_partners.ids)],
            fields=['partner_id'], groupby=['partner_id'],
        )
        self.project_count = 0
        for group in groups:
            partner = self.browse(group['partner_id'][0])
            while partner:
                if partner in self:
                    partner.project_count += group['partner_id_count']
                partner = partner.parent_id

    def action_open_project_config(self):
        action = self.env["ir.actions.actions"]._for_xml_id("project.open_view_project_all_config")
        action['context'] = {}
        all_child = self.with_context(active_test=False).search([('id', 'child_of', self.ids)])
        action['domain'] = ['|', ('partner_id', 'in', self.ids), ('partner_id', 'in', all_child.ids)]
        return action
