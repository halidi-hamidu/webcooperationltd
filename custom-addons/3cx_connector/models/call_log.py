from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta

class CallLog(models.Model):
    _name = 'call.log'
    _description = '3CX Call Log'
    _order = 'start_time desc'

    partner_id = fields.Many2one('res.partner', 'Partner')
    phone = fields.Char('Phone Number', required=True)
    direction = fields.Selection([
        ('in', 'Inbound'),
        ('out', 'Outbound')
    ], string='Direction', required=True)
    start_time = fields.Datetime('Start Time', required=True)
    end_time = fields.Datetime('End Time')
    duration = fields.Integer('Duration (seconds)', compute='_compute_duration', store=True)
    status = fields.Selection([
        ('answered', 'Answered'),
        ('missed', 'Missed'),
        ('failed', 'Failed')
    ], string='Status', required=True)
    recording_url = fields.Char('Recording URL')
    notes = fields.Text('Notes')
    user_id = fields.Many2one('res.users', string='Agent', default=lambda self: self.env.user)
    team_id = fields.Many2one('crm.team', string='Sales Team', related='user_id.sale_team_id', store=True)

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for log in self:
            log.duration = (log.end_time - log.start_time).total_seconds() if log.end_time and log.start_time else 0

    def _generate_call_metrics_report(self):
        """Generate daily call metrics for teams"""
        teams = self.env['crm.team'].search([])
        for team in teams:
            calls = self.search([
                ('team_id', '=', team.id),
                ('start_time', '>=', fields.Date.today() - relativedelta(days=1))
            ])
            
            answered = calls.filtered(lambda c: c.status == 'answered')
            avg_duration = sum(answered.mapped('duration')) / len(answered) if answered else 0
            
            self.env['call.metrics'].create({
                'team_id': team.id,
                'date': fields.Date.today(),
                'total_calls': len(calls),
                'answered_calls': len(answered),
                'missed_calls': len(calls.filtered(lambda c: c.status == 'missed')),
                'avg_duration': avg_duration,
            })