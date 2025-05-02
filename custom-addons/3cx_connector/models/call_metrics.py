from odoo import models, fields, api

class CallMetrics(models.Model):
    _name = 'call.metrics'
    _description = 'Call Performance Metrics'
    _order = 'date desc'

    team_id = fields.Many2one('crm.team', string='Team', required=True)
    date = fields.Date('Report Date', default=fields.Date.today)
    total_calls = fields.Integer('Total Calls')
    answered_calls = fields.Integer('Answered Calls')
    missed_calls = fields.Integer('Missed Calls')
    avg_duration = fields.Float('Avg Duration (s)')
    conversion_rate = fields.Float('Answer Rate', compute='_compute_conversion_rate')

    @api.depends('answered_calls', 'total_calls')
    def _compute_conversion_rate(self):
        for record in self:
            record.conversion_rate = (record.answered_calls / record.total_calls * 100) if record.total_calls else 0