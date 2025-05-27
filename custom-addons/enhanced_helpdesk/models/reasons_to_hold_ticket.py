from odoo import models, fields

class TicketHoldReason(models.Model):
    _name = 'helpdesk.ticket.hold.reason'
    _description = 'Reason for Putting Ticket on Hold'
    _order = 'name'

    name = fields.Char(string="Reason", required=True)
    active = fields.Boolean(default=True)