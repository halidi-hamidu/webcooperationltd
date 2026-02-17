from odoo import models, fields, api
from datetime import datetime


class HelpdeskTicketTagTransfer(models.Model):
    _name = 'helpdesk.ticket.tag.transfer'
    _description = 'Helpdesk Ticket Tag Transfer Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_tagged desc'
    _rec_name = 'tagged_user_id'

    ticket_id = fields.Many2one(
        'helpdesk.ticket', 
        string='Ticket', 
        required=True, 
        ondelete='cascade'
    )
    tagged_user_id = fields.Many2one(
        'res.users', 
        string='Tagged User', 
        required=True,
        help='User who was tagged in the chatter'
    )
    tagged_by_user_id = fields.Many2one(
        'res.users', 
        string='Tagged By', 
        required=True,
        help='User who tagged the other user'
    )
    date_tagged = fields.Datetime(
        string='Date & Time Tagged', 
        default=fields.Datetime.now, 
        required=True
    )
    action = fields.Selection([
        ('pending', 'Pending'),
        ('accept', 'Accept'),
        ('reject', 'Reject'),
        ('hold', 'Hold'),
        ('in_progress', 'In Progress'),
        ('closed', 'Closed')
    ], string='Action', default='pending', required=True)
    
    response_time = fields.Datetime(
        string='Response Time',
        help='Date and time when the tagged user responded'
    )
    accepted_at = fields.Datetime(
        string='Accepted At',
        help='Date and time when the user accepted the assignment'
    )
    rejected_at = fields.Datetime(
        string='Rejected At',
        help='Date and time when the user rejected the assignment'
    )
    held_at = fields.Datetime(
        string='Put on Hold At',
        help='Date and time when the user put the assignment on hold'
    )
    closed_at = fields.Datetime(
        string='Closed At',
        help='Date and time when the user closed/completed the assignment'
    )
    response_duration = fields.Float(
        string='Response Duration (Hours)',
        compute='_compute_response_duration',
        store=True,
        help='Time taken to respond in hours'
    )
    resolution_time = fields.Float(
        string='Resolution Time (Hours)',
        compute='_compute_resolution_time',
        store=True,
        help='Time taken to close/resolve the assignment in hours'
    )
    
    # Additional information fields
    message_id = fields.Many2one(
        'mail.message',
        string='Related Message',
        help='The message where the user was tagged'
    )
    notes = fields.Text(string='Notes')
    
    # Hold-related fields
    hold_reasons_ids = fields.Many2many(
        'helpdesk.hold.reason',
        string='Hold Reasons',
        help='Selected reasons for putting assignment on hold'
    )
    hold_details = fields.Text(
        string='Hold Details',
        help='Additional details provided when putting assignment on hold'
    )
    hold_timestamp = fields.Datetime(
        string='Hold Timestamp',
        help='When the assignment was put on hold'
    )
    
    # Rejection-related fields
    rejection_reason = fields.Text(
        string='Rejection Reason',
        help='Reason provided when rejecting the assignment'
    )
    rejection_reasons_ids = fields.Many2many(
        'helpdesk.rejection.reason',
        string='Rejection Reasons',
        help='Selected reasons for rejecting assignment'
    )
    
    # Team field - shows which team the tagged user belongs to
    team_id = fields.Many2one(
        'helpdesk.team',
        string='User Team',
        compute='_compute_team_id',
        store=True,
        help='Team that the tagged user belongs to'
    )
    
    # Button visibility control
    can_user_act = fields.Boolean(
        string='Can User Act',
        compute='_compute_can_user_act',
        help='Determines if current user can act on this tag assignment'
    )
    
    @api.depends('tagged_user_id')
    def _compute_can_user_act(self):
        """Compute if current user can act on this tag assignment"""
        for record in self:
            # Allow if user is the tagged user or is admin
            is_tagged_user = record.tagged_user_id.id == self.env.user.id
            is_admin = self.env.user.has_group('base.group_system')
            record.can_user_act = is_tagged_user or is_admin
    
    @api.depends('tagged_user_id')
    def _compute_team_id(self):
        """Compute the team that the tagged user belongs to"""
        for record in self:
            if record.tagged_user_id:
                # Find teams where this user is a member
                teams = self.env['helpdesk.team'].search([
                    ('member_ids', 'in', record.tagged_user_id.id)
                ], limit=1)
                if teams:
                    record.team_id = teams.id
                else:
                    record.team_id = False
            else:
                record.team_id = False
    
    @api.depends('date_tagged', 'response_time')
    def _compute_response_duration(self):
        for record in self:
            if record.date_tagged and record.response_time:
                delta = record.response_time - record.date_tagged
                record.response_duration = delta.total_seconds() / 3600  # Convert to hours
            else:
                record.response_duration = 0.0
    
    @api.depends('date_tagged', 'closed_at')
    def _compute_resolution_time(self):
        for record in self:
            if record.date_tagged and record.closed_at:
                delta = record.closed_at - record.date_tagged
                record.resolution_time = delta.total_seconds() / 3600  # Convert to hours
            else:
                record.resolution_time = 0.0

    def action_accept(self):
        """Show confirmation dialog for accepting the transfer"""
        self.ensure_one()
        
        # Create wizard record
        wizard = self.env['helpdesk.transfer.accept.wizard'].create({
            'tag_transfer_id': self.id,
        })
        
        return {
            'name': 'Confirm Transfer Accept',
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.transfer.accept.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
    
    def do_accept(self):
        """Actually perform the acceptance (called from wizard)"""
        self.ensure_one()
        now = fields.Datetime.now()
        self.write({
            'action': 'accept',
            'response_time': now,
            'accepted_at': now
        })
        
        # Post a message to the ticket
        self.ticket_id.message_post(
            body=f"🟢 <b>{self.tagged_user_id.name}</b> accepted the tag assignment from <b>{self.tagged_by_user_id.name}</b> at {now.strftime('%Y-%m-%d %H:%M:%S')}",
            subtype_xmlid="mail.mt_note"
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Tag assignment accepted successfully!',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_reject(self):
        """Show rejection dialog with reason selection"""
        self.ensure_one()
        
        # Create wizard record
        wizard = self.env['helpdesk.transfer.reject.wizard'].create({
            'tag_transfer_id': self.id,
        })
        
        return {
            'name': 'Reject Transfer Request',
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.transfer.reject.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_hold(self):
        """Show confirmation dialog before opening hold wizard"""
        self.ensure_one()
        
        # Create confirmation wizard
        confirmation_wizard = self.env['helpdesk.hold.confirmation.wizard'].create({
            'tag_transfer_id': self.id,
            'tagged_user_name': self.tagged_user_id.name,
            'ticket_name': self.ticket_id.name,
        })
        
        return {
            'name': 'Confirm Hold Action',
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.hold.confirmation.wizard',
            'res_id': confirmation_wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_close(self):
        """Open wizard to close/complete the assignment"""
        self.ensure_one()
        
        # Create wizard record
        wizard = self.env['helpdesk.transfer.close.wizard'].create({
            'tag_transfer_id': self.id,
        })
        
        return {
            'name': 'Close Assignment',
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.transfer.close.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_view_details(self):
        """View details of held/rejected transfer"""
        self.ensure_one()
        
        # Create wizard record
        wizard = self.env['helpdesk.transfer.details.wizard'].create({
            'tag_transfer_id': self.id,
        })
        
        return {
            'name': 'Transfer Details',
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.transfer.details.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
        
    def action_unhold_ticket(self):
        """Action to remove ticket from hold and resume SLA"""
        self.ensure_one()
        
        # Find the 'In Progress' stage
        in_progress_stage = self.env.ref('helpdesk.stage_in_progress', raise_if_not_found=False)
        if not in_progress_stage:
            # Try to find any stage with 'In Progress' or 'progress' in the name
            in_progress_stage = self.env['helpdesk.stage'].search([
                '|', ('name', 'ilike', 'progress'),
                     ('name', 'ilike', 'in progress')
            ], limit=1)
        
        if in_progress_stage:
            # Update the ticket stage
            self.ticket_id.write({'stage_id': in_progress_stage.id})
            
            # Update this tag transfer record to in_progress
            self.write({'action': 'in_progress'})
            
            # Update any other tag transfer records that are on hold to in_progress
            other_hold_transfers = self.ticket_id.tag_transfer_ids.filtered(
                lambda t: t.action == 'hold' and t.id != self.id
            )
            if other_hold_transfers:
                other_hold_transfers.write({'action': 'in_progress'})
            
            # End any active hold logs on the ticket
            active_hold_logs = self.ticket_id.hold_time_logs.filtered(lambda log: not log.end_time)
            if active_hold_logs:
                now = fields.Datetime.now()
                active_hold_logs.write({'end_time': now})
                
                # Recompute hold time
                self.ticket_id._compute_total_hold_time()
                
                # Recalculate SLA status
                self.ticket_id._compute_sla_status()
            
            # Post a message to the ticket
            self.ticket_id.message_post(
                body=f"⏯️ Ticket removed from hold by <b>{self.env.user.name}</b>. SLA timer resumed.",
                subtype_xmlid="mail.mt_note"
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Action Completed',
                    'message': 'Ticket has been removed from hold and SLA timer resumed. Page will refresh to show changes.',
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    }
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': 'Could not find In Progress stage to move ticket to.',
                    'type': 'warning',
                    'sticky': False,
                }
            }



    @api.depends('tagged_user_id', 'tagged_by_user_id')
    def _compute_display_name(self):
        for record in self:
            tagged = record.tagged_user_id.name or ''
            tagged_by = record.tagged_by_user_id.name or ''
            record.display_name = f"{tagged} tagged by {tagged_by}"
        
    @api.model
    def create_transfer_from_mention(self, ticket_id, tagged_user_id, tagged_by_user_id, message_id=None):
        """Create a transfer line when a user is mentioned"""
        import logging
        _logger = logging.getLogger(__name__)
        
        _logger.info(f"DEBUG: create_transfer_from_mention called with ticket_id={ticket_id}, tagged_user_id={tagged_user_id}, tagged_by_user_id={tagged_by_user_id}")
        
        # Check if transfer already exists for this combination
        existing = self.search([
            ('ticket_id', '=', ticket_id),
            ('tagged_user_id', '=', tagged_user_id),
            ('tagged_by_user_id', '=', tagged_by_user_id),
            ('action', '=', 'pending')
        ])
        
        if not existing:
            transfer = self.create({
                'ticket_id': ticket_id,
                'tagged_user_id': tagged_user_id,
                'tagged_by_user_id': tagged_by_user_id,
                'message_id': message_id,
                'action': 'pending'
            })
            _logger.info(f"DEBUG: Created new transfer record with ID {transfer.id}")
            return transfer
        else:
            _logger.info(f"DEBUG: Transfer already exists with ID {existing.id}")
            return existing
    
    @api.model
    def test_create_transfer(self, ticket_id):
        """Test method to manually create a transfer for testing"""
        # Get current user and admin user for testing
        current_user = self.env.user
        admin_user = self.env.ref('base.user_admin')
        
        if current_user.id != admin_user.id:
            # Create a transfer where admin tags current user
            return self.create_transfer_from_mention(
                ticket_id=ticket_id,
                tagged_user_id=current_user.id,
                tagged_by_user_id=admin_user.id,
                message_id=None
            )
        else:
            # If admin is current user, find another user
            other_user = self.env['res.users'].search([('id', '!=', admin_user.id)], limit=1)
            if other_user:
                return self.create_transfer_from_mention(
                    ticket_id=ticket_id,
                    tagged_user_id=other_user.id,
                    tagged_by_user_id=admin_user.id,
                    message_id=None
                )