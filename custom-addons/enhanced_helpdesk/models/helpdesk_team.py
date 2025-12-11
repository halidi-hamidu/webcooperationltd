from odoo import models, fields, api

class CustomHelpdeskTeam(models.Model):
    _inherit = 'helpdesk.team'
    
    team_type_ids = fields.Many2many(
        'helpdesk.ticket.type',
        'helpdesk_team_ticket_type_rel',
        'team_id',
        'type_id',
        string='Team Types',
        help='Ticket types associated with this helpdesk team'
    )