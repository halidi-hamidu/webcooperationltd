from odoo import models, fields

class VtsOperationTeam(models.Model):
    _name = 'vts.operation.team'
    _description = 'VTS Operation Team'

    name = fields.Char(string='Team Name', required=True)
    user_id = fields.Many2one('res.users', string='Team Leader', required=True)
    member_ids = fields.Many2many('res.users', string='Team Members')