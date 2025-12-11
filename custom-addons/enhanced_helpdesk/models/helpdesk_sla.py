from odoo import models, fields

class CustomHelpdeskSLA(models.Model):
    _inherit = 'helpdesk.sla'

    description = fields.Html(string='Description')
    working_time_id = fields.Many2one(
    'helpdesk.working.time',
    string="Working Time"
)
