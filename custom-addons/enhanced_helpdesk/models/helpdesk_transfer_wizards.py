from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime


class HelpdeskTransferAcceptWizard(models.TransientModel):
    _name = 'helpdesk.transfer.accept.wizard'
    _description = 'Accept Transfer Confirmation Wizard'

    tag_transfer_id = fields.Many2one(
        'helpdesk.ticket.tag.transfer',
        string='Tag Transfer',
        required=True
    )
    
    ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string='Ticket',
        related='tag_transfer_id.ticket_id',
        readonly=True
    )
    
    tagged_user_id = fields.Many2one(
        'res.users',
        string='Tagged User',
        related='tag_transfer_id.tagged_user_id',
        readonly=True
    )
    
    tagged_by_user_id = fields.Many2one(
        'res.users',
        string='Tagged By',
        related='tag_transfer_id.tagged_by_user_id',
        readonly=True
    )
    
    date_tagged = fields.Datetime(
        string='Date Tagged',
        related='tag_transfer_id.date_tagged',
        readonly=True
    )
    
    def action_confirm_accept(self):
        """Confirm acceptance of the transfer request"""
        self.ensure_one()
        self.tag_transfer_id.do_accept()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def action_cancel(self):
        """Cancel the acceptance"""
        return {'type': 'ir.actions.act_window_close'}


class HelpdeskTransferRejectWizard(models.TransientModel):
    _name = 'helpdesk.transfer.reject.wizard'
    _description = 'Reject Transfer Wizard'

    tag_transfer_id = fields.Many2one(
        'helpdesk.ticket.tag.transfer',
        string='Tag Transfer',
        required=True
    )
    
    ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string='Ticket',
        related='tag_transfer_id.ticket_id',
        readonly=True
    )
    
    tagged_user_id = fields.Many2one(
        'res.users',
        string='Tagged User',
        related='tag_transfer_id.tagged_user_id',
        readonly=True
    )
    
    tagged_by_user_id = fields.Many2one(
        'res.users',
        string='Tagged By',
        related='tag_transfer_id.tagged_by_user_id',
        readonly=True
    )
    
    rejection_reason = fields.Text(
        string='Reason for Rejection',
        required=False,
        help='Please explain why you are rejecting this transfer request'
    )
    
    predefined_reasons = fields.Many2many(
        'helpdesk.rejection.reason',
        string='Select Applicable Reasons',
        help='Select all reasons that apply for this rejection'
    )
    
    def action_confirm_reject(self):
        """Confirm rejection with reason"""
        self.ensure_one()
        
        if not self.rejection_reason and not self.predefined_reasons:
            
            raise ValidationError('Please provide a reason for rejection by either selecting predefined reasons or writing additional details.')
        
        # Store rejection details
        now = fields.Datetime.now()
        reason_text = self.rejection_reason or ''
        if self.predefined_reasons:
            predefined_text = ', '.join(self.predefined_reasons.mapped('name'))
            reason_text = f"{predefined_text}\n{reason_text}".strip()
        
        self.tag_transfer_id.write({
            'action': 'reject',
            'response_time': now,
            'rejected_at': now,
            'rejection_reason': reason_text,
            'rejection_reasons_ids': [(6, 0, self.predefined_reasons.ids)]
        })
        
        # Post a message to the ticket
        self.tag_transfer_id.ticket_id.message_post(
            body=f"🔴 <b>{self.tag_transfer_id.tagged_user_id.name}</b> rejected the tag assignment from <b>{self.tag_transfer_id.tagged_by_user_id.name}</b> at {now.strftime('%Y-%m-%d %H:%M:%S')}\n<br/><br/><b>Reason:</b> {reason_text}",
            subtype_xmlid="mail.mt_note"
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def action_cancel(self):
        """Cancel the rejection"""
        return {'type': 'ir.actions.act_window_close'}


class HelpdeskTransferDetailsWizard(models.TransientModel):
    _name = 'helpdesk.transfer.details.wizard'
    _description = 'View Transfer Details Wizard'

    tag_transfer_id = fields.Many2one(
        'helpdesk.ticket.tag.transfer',
        string='Tag Transfer',
        required=True
    )
    
    ticket_id = fields.Many2one(
        'helpdesk.ticket',
        string='Ticket',
        related='tag_transfer_id.ticket_id',
        readonly=True
    )
    
    tagged_user_id = fields.Many2one(
        'res.users',
        string='Tagged User',
        related='tag_transfer_id.tagged_user_id',
        readonly=True
    )
    
    tagged_by_user_id = fields.Many2one(
        'res.users',
        string='Tagged By',
        related='tag_transfer_id.tagged_by_user_id',
        readonly=True
    )
    
    action = fields.Selection(
        related='tag_transfer_id.action',
        readonly=True
    )
    
    date_tagged = fields.Datetime(
        string='Date Tagged',
        related='tag_transfer_id.date_tagged',
        readonly=True
    )
    
    response_time = fields.Datetime(
        string='Response Time',
        related='tag_transfer_id.response_time',
        readonly=True
    )
    
    # Hold-related fields
    hold_reasons_ids = fields.Many2many(
        'helpdesk.hold.reason',
        related='tag_transfer_id.hold_reasons_ids',
        readonly=True
    )
    
    hold_details = fields.Text(
        string='Hold Details',
        related='tag_transfer_id.hold_details',
        readonly=True
    )
    
    held_at = fields.Datetime(
        string='Put on Hold At',
        related='tag_transfer_id.held_at',
        readonly=True
    )
    
    # Rejection-related fields
    rejection_reason = fields.Text(
        string='Rejection Reason',
        related='tag_transfer_id.rejection_reason',
        readonly=True
    )
    
    rejection_reasons_ids = fields.Many2many(
        'helpdesk.rejection.reason',
        related='tag_transfer_id.rejection_reasons_ids',
        readonly=True
    )
    
    rejected_at = fields.Datetime(
        string='Rejected At',
        related='tag_transfer_id.rejected_at',
        readonly=True
    )
    
    def action_close(self):
        """Close the details view"""
        return {'type': 'ir.actions.act_window_close'}


class HelpdeskRejectionReason(models.Model):
    _name = 'helpdesk.rejection.reason'
    _description = 'Helpdesk Rejection Reason'
    _order = 'sequence, name'

    name = fields.Char(string='Reason', required=True)
    description = fields.Text(string='Description')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)