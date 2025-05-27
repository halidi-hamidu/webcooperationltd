from odoo import models, fields, api
from odoo.tools.translate import _
class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'
    
    stage_id = fields.Many2one(
        'helpdesk.stage',
        string='Stage',
           domain="[('name', '!=', 'New')]",
    )
    reason_description_to_hold_ticket = fields.Text(string='Reason to Hold Ticket')
    common_reasons_to_hold_ticket =  fields.Many2many(
        'helpdesk.ticket.hold.reason',
        string='Common Reasons to Hold Ticket'
    )
    sla_description = fields.Html(string='SLA Description', compute="_compute_sla_description")
    transfer_ids = fields.One2many('helpdesk.ticket.transfer', 'ticket_id', string='Ticket Transfers History')
    sla_breached = fields.Boolean(string="SLA Breached", default=False)
    sla_breach_time = fields.Datetime(string="SLA Breach Time")
    is_on_hold = fields.Boolean(compute='_compute_is_on_hold', store=True)

    @api.depends('stage_id')
    def _compute_is_on_hold(self):
        for rec in self:
            rec.is_on_hold = rec.stage_id.name == 'On Hold'

    @api.model
    def _check_sla_breaches(self):
        now = fields.Datetime.now()
        tickets = self.search([
            ('sla_deadline', '<', now),
            ('sla_breached', '=', False),
            ('stage_id.fold', '=', False)  # Only open tickets
        ])

        template = self.env.ref('enhanced_helpdesk.email_template_sla_breach', raise_if_not_found=False)

        for ticket in tickets:
            ticket.sla_breach_time = now
            ticket.message_post(
                body=_(
                    "<b>SLA Breach:</b> Ticket has exceeded its SLA deadline (%s)." %
                    ticket.sla_deadline.strftime('%Y-%m-%d %H:%M:%S')
                ),
                subtype_xmlid="mail.mt_note"
            )
            if template:
                template.send_mail(ticket.id, force_send=True)
            ticket.sla_breached = True

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
        
        
