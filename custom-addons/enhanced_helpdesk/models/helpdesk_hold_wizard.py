from odoo import models, fields, api
from markupsafe import Markup, escape


class HelpdeskTicketHoldWizard(models.TransientModel):
    _name = 'helpdesk.ticket.hold.wizard'
    _description = 'Hold Tag Assignment Wizard'

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
    
    hold_reason = fields.Text(
        string='Reason for Hold',
        help='Please describe why you are putting this assignment on hold'
    )
    
    predefined_reasons = fields.Many2many(
        'helpdesk.hold.reason',
        string='Select Applicable Reasons',
        help='Select all predefined reasons that apply'
    )
    
    # Success message display
    success_message = fields.Text(
        string='Status Message',
        readonly=True,
        help='Display success or status messages'
    )
    
    show_success_info = fields.Boolean(
        string='Show Success Info',
        default=False,
        help='Flag to show success message section'
    )
    
    @api.model
    def default_get(self, fields_list):
        """Override to handle context values and auto-refresh functionality"""
        result = super().default_get(fields_list)
        
        # Handle success message from context (after submit)
        if self.env.context.get('show_success_message'):
            result['success_message'] = self.env.context.get('success_message', '')
            result['show_success_info'] = True
            
        return result
    
    def action_refresh_wizard(self):
        """Action to refresh the wizard - used for auto-refresh functionality"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Hold Assignment',
            'res_model': 'helpdesk.ticket.hold.wizard',
            'view_mode': 'form',
            'target': 'new',
            'res_id': self.id,
            'context': dict(
                self.env.context,
                default_ticket_id=self.ticket_id.id,
                default_tag_transfer_id=self.tag_transfer_id.id,
            ),
        }
    
    def action_clear_form(self):
        """Clear the form fields after successful submission"""
        self.ensure_one()
        self.write({
            'predefined_reasons': [(6, 0, [])],  # Clear many2many field
            'hold_reason': '',
            'success_message': '',
            'show_success_info': False,
        })
        return self.action_refresh_wizard()
    
    def action_submit_hold(self):
        """Submit the hold request with reasons and post to chatter"""
        self.ensure_one()
        
        # Validation: Ensure at least one reason is provided or additional details
        if not self.predefined_reasons and not self.hold_reason:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Please select at least one hold reason or provide additional details.',
                    'type': 'warning',
                    'sticky': True,
                }
            }
        
        now = fields.Datetime.now()
        
        # Update the tag transfer record with hold information
        self.tag_transfer_id.write({
            'action': 'hold',
            'response_time': now,
            'held_at': now
        })
        
        # Save hold reasons and details to the tag transfer record for future reference
        hold_data = {
            'hold_reasons_ids': [(6, 0, self.predefined_reasons.ids)],
            'hold_details': self.hold_reason,
            'hold_timestamp': now
        }
        self.tag_transfer_id.write(hold_data)
        
        # IMPORTANT: Also change the ticket stage to "On Hold" to pause SLA counting
        # Find the "On Hold" stage
        on_hold_stage = self.env['helpdesk.stage'].search([
            ('name', '=', 'On Hold')
        ], limit=1)
        
        if on_hold_stage:
            # Use the predefined reasons directly (helpdesk.hold.reason model)
            ticket_hold_reasons = []
            if self.predefined_reasons:
                ticket_hold_reasons = self.predefined_reasons.ids
            
            # Update ticket stage and hold reasons
            ticket_update_vals = {
                'stage_id': on_hold_stage.id,
            }
            
            # Add hold reasons if found
            if ticket_hold_reasons:
                ticket_update_vals['common_reasons_to_hold_ticket'] = [(6, 0, ticket_hold_reasons)]
            
            # Add hold description if provided
            if self.hold_reason:
                ticket_update_vals['reason_description_to_hold_ticket'] = self.hold_reason
                
            # Update the ticket
            self.ticket_id.write(ticket_update_vals)
        
        # Build structured message for chatter
        user_name = self.tagged_user_id.name
        tagged_by_name = self.tag_transfer_id.tagged_by_user_id.name
        timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
        
        # Create professional message structure
        message_parts = [
            Markup("<div class='alert alert-warning'>"),
            Markup("<h5><i class='fa fa-pause-circle'></i> Assignment Put On Hold</h5>"),
            Markup("<p><strong>{user}</strong> put the tag assignment from <strong>{by}</strong> on hold</p>").format(
                user=user_name, by=tagged_by_name),
            Markup("<small class='text-muted'><i class='fa fa-clock-o'></i> {ts}</small>").format(ts=timestamp_str),
            Markup("</div>")
        ]
        
        # Section 1: Hold Reasons
        if self.predefined_reasons:
            message_parts.append(Markup("<div class='mt-3'>"))
            message_parts.append(Markup("<h6><i class='fa fa-list-check text-warning'></i> Selected Hold Reasons:</h6>"))
            message_parts.append(Markup("<ul class='mb-0'>"))
            for reason in self.predefined_reasons:
                description = Markup(" - {desc}").format(desc=reason.description) if reason.description else Markup("")
                message_parts.append(Markup("<li><strong>{name}</strong>{desc}</li>").format(
                    name=reason.name, desc=description))
            message_parts.append(Markup("</ul>"))
            message_parts.append(Markup("</div>"))
        
        # Section 2: Additional Details
        if self.hold_reason:
            message_parts.append(Markup("<div class='mt-3'>"))
            message_parts.append(Markup("<h6><i class='fa fa-edit text-primary'></i> Additional Details:</h6>"))
            message_parts.append(Markup("<div class='border-left border-primary pl-3'>"))
            # Convert line breaks to HTML, escaping user content first
            formatted_details = Markup("<br/>").join(escape(line) for line in self.hold_reason.split('\n'))
            message_parts.append(Markup("<p>{details}</p>").format(details=formatted_details))
            message_parts.append(Markup("</div>"))
            message_parts.append(Markup("</div>"))
        
        message_body = Markup("").join(message_parts)
        
        # Get all involved users for notification
        tagged_users = self.ticket_id.tag_transfer_ids.mapped('tagged_user_id')
        tagged_by_users = self.ticket_id.tag_transfer_ids.mapped('tagged_by_user_id')
        all_users = (tagged_users | tagged_by_users).filtered(lambda u: u.id != self.env.user.id)
        
        # Post structured message to ticket chatter
        message = self.ticket_id.message_post(
            body=message_body,
            subtype_xmlid="mail.mt_note",
            partner_ids=all_users.mapped('partner_id').ids,
            subject=f"🔄 Assignment Hold Request - {self.ticket_id.name}"
        )
        
        # Return success notification
        reasons_count = len(self.predefined_reasons)
        has_details = bool(self.hold_reason)
        
        success_msg = f"Hold request submitted successfully!"
        if reasons_count > 0:
            success_msg += f" ({reasons_count} reason{'s' if reasons_count > 1 else ''} selected"
            if has_details:
                success_msg += " + additional details"
            success_msg += ")"
        elif has_details:
            success_msg += " (Additional details provided)"
        
        # Clear form fields and show success message
        self.write({
            'predefined_reasons': [(6, 0, [])],  # Clear many2many field
            'hold_reason': '',
            'success_message': success_msg,
            'show_success_info': True,
        })
        
        # Return action to close all wizards and refresh the page
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
            'params': {
                'message': success_msg,
                'type': 'success',
                'title': 'Hold Request Submitted!',
            }
        }


class HelpdeskHoldReason(models.Model):
    _name = 'helpdesk.hold.reason'
    _description = 'Predefined Hold Reasons'
    _order = 'sequence, name'

    name = fields.Char(
        string='Reason',
        required=True,
        help='Predefined reason for putting assignments on hold'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Used to order the reasons'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    description = fields.Text(
        string='Description',
        help='Additional details about this hold reason'
    )