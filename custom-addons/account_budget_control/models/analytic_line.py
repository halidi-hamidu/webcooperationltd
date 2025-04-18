# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class AccountAnalyticLine(models.Model):
     _inherit = 'account.analytic.line'

     crossovered_budget_line = fields.Many2one('crossovered.budget.lines', 'Budget Line',related="move_line_id.budget_line_id",store=True)