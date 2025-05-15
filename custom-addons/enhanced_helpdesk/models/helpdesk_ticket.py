from odoo import models, fields, api
class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'
    
    
    sla_description = fields.Html(string='SLA Description', compute="_compute_sla_description")

    @api.depends('ticket_type_id')
    def _compute_sla_description(self):
        # self.sla_description  = "DEmo description"
        for ticket in self:
            sla = self.env['helpdesk.sla'].search([
                ('ticket_type_ids', '=', ticket.ticket_type_id.id)
            ], limit=1)
            ticket.sla_description = sla.description if sla else ''
            
    @api.onchange('team_id')
    def _onchange_team_id(self):
        self.ticket_type_id = False