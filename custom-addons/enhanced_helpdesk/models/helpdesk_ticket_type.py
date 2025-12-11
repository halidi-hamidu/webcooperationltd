from odoo import models, fields, api

class HelpdeskTicketType(models.Model):
    _inherit = 'helpdesk.ticket.type'
    
    user_ids = fields.Many2many(
        'res.users',
        'helpdesk_ticket_type_user_rel',  # Relation table name
        'ticket_type_id',                 # Column in relation table pointing to ticket type
        'user_id',                        # Column in relation table pointing to user
        string='Assigned Users',
        help='Users assigned to handle tickets of this type.'
    )
    
    user_count = fields.Integer(
        string='User Count',
        compute='_compute_user_count',
        store=False
    )
    team_ids = fields.Many2many(
        'helpdesk.team',
        'helpdesk_ticket_type_team_rel',
        'ticket_type_id',
        'team_id',
        string='Assigned Teams',
        help='Teams assigned to handle tickets of this type.'
    )
    @api.depends('user_ids')
    def _compute_user_count(self):
        for record in self:
            record.user_count = len(record.user_ids)
