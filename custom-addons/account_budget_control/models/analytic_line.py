from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    budget_line_id = fields.Many2one(
        'budget.line', 'Budget Line',
        related="move_line_id.budget_line_id", store=True)