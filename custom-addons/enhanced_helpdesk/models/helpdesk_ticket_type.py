from odoo import models, fields

class HelpdeskTicketType(models.Model):
    _inherit = 'helpdesk.ticket.type'
    
    team_ids = fields.Many2many(
        'helpdesk.team',
        'helpdesk_ticket_type_team_rel',  # Relation table (optional name)
        'ticket_type_id',                 # Column in relation table pointing to ticket type
        'team_id',                        # Column in relation table pointing to helpdesk team
        string='Helpdesk Teams',
        help='Associate this ticket type with one or more helpdesk teams.'
    )
