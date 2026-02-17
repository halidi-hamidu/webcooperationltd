from odoo import models, fields, api


class HelpdeskHoldConfirmationWizard(models.TransientModel):
    _name = 'helpdesk.hold.confirmation.wizard'
    _description = 'Hold Confirmation Dialog'

    tag_transfer_id = fields.Many2one(
        'helpdesk.ticket.tag.transfer',
        string='Tag Transfer',
        required=True
    )
    
    tagged_user_name = fields.Char(
        string='Tagged User',
        readonly=True
    )
    
    ticket_name = fields.Char(
        string='Ticket',
        readonly=True
    )
    
    def action_confirm_hold(self):
        """Confirm and proceed with hold action"""
        self.ensure_one()
        
        # Create hold wizard record
        wizard = self.env['helpdesk.ticket.hold.wizard'].create({
            'tag_transfer_id': self.tag_transfer_id.id,
        })
        
        return {
            'name': 'Put Assignment On Hold',
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.ticket.hold.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self.env.context, from_confirmation=True),
        }
    
    def action_cancel_hold(self):
        """Cancel hold action and refresh the page"""
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
            'params': {
                'message': 'Hold action cancelled',
                'type': 'info',
            }
        }