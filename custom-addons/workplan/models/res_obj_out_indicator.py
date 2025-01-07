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


class WorkplanObjective(models.Model):
    _name = 'workplan.objective'
    _order = "name"
    _description = "Objective"

    name = fields.Char('Name', required=True)
    outcome_ids = fields.One2many('workplan.outcome', 'objective_id', string='Outcomes/Targets',)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    

class WorkplanOutcome(models.Model):
    _name = 'workplan.outcome'
    _order = "name"
    _description = "Outcome / Target"

    name = fields.Char('Name', required=True)
    objective_id = fields.Many2one('workplan.objective', 'Objective', required=True)
    indicator_ids = fields.One2many('workplan.indicator', 'outcome_id', string='Indicator',)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)


class WorkplanIndicator(models.Model):
    _name = 'workplan.indicator'
    _order = "name"
    _description = "Indicator"

    name = fields.Char('Name', required=True)
    description = fields.Char('Description')
    outcome_id = fields.Many2one('workplan.outcome', 'Outcome', required=True)
    objective_id = fields.Many2one('workplan.objective', 'Objective', related='outcome_id.objective_id')
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    
