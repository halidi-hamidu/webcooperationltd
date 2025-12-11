from odoo import models, fields, api

class HelpdeskWorkingTimeWizard(models.TransientModel):
    _name = 'helpdesk.working.time.wizard'
    _description = 'Helpdesk Working Time Configuration Wizard'

    working_time_id = fields.Many2one(
        'helpdesk.working.time',
        string='Working Time Configuration',
        required=True,
        help='Select working time configuration to apply'
    )
    ticket_ids = fields.Many2many(
        'helpdesk.ticket',
        string='Tickets to Update',
        help='Tickets that will be updated with the selected working time configuration'
    )
    recalculate_sla = fields.Boolean(
        string='Recalculate SLA Deadlines',
        default=True,
        help='If checked, SLA deadlines will be recalculated based on working time'
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        # Get active ticket IDs from context
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['ticket_ids'] = [(6, 0, active_ids)]
            
        # Set default working time if only one exists
        working_times = self.env['helpdesk.working.time'].search([
            ('company_id', '=', self.env.company.id),
            ('active', '=', True)
        ])
        if len(working_times) == 1:
            res['working_time_id'] = working_times.id
            
        return res

    def action_apply_working_time(self):
        """Apply working time configuration to selected tickets"""
        if not self.ticket_ids or not self.working_time_id:
            return {'type': 'ir.actions.act_window_close'}
            
        for ticket in self.ticket_ids:
            ticket.working_time_config_id = self.working_time_id.id
            
            if self.recalculate_sla:
                ticket._recalculate_sla_with_working_time()
                
        # Show success message
        message = f"Working time configuration applied to {len(self.ticket_ids)} ticket(s)"
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
