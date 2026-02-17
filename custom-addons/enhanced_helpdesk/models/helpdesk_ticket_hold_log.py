from odoo import models, fields, api
from datetime import timedelta


class HelpdeskTicketHoldLog(models.Model):
    _name = 'helpdesk.ticket.hold.log'
    _description = 'Helpdesk Ticket Hold Time Log'
    _order = 'start_time desc'
    
    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', required=True, ondelete='cascade')
    start_time = fields.Datetime(string='Hold Start Time', required=True)
    end_time = fields.Datetime(string='Hold End Time')
    reason = fields.Text(string='Hold Reason')
    duration_hours = fields.Float(
        string='Duration (Hours)', 
        compute='_compute_duration_hours', 
        store=True,
        help='Duration of hold period in hours'
    )
    
    @api.depends('start_time', 'end_time')
    def _compute_duration_hours(self):
        for log in self:
            if log.start_time:
                end_time = log.end_time or fields.Datetime.now()
                duration = end_time - log.start_time
                log.duration_hours = duration.total_seconds() / 3600
            else:
                log.duration_hours = 0.0