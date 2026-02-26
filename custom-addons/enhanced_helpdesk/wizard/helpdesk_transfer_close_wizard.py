from odoo import models, fields, api
from markupsafe import Markup, escape


class HelpdeskTransferCloseWizard(models.TransientModel):
    _name = 'helpdesk.transfer.close.wizard'
    _description = 'Close Tag Transfer Wizard'

    tag_transfer_id = fields.Many2one(
        'helpdesk.ticket.tag.transfer',
        string='Tag Transfer',
        required=True
    )
    ticket_id = fields.Many2one(
        'helpdesk.ticket',
        related='tag_transfer_id.ticket_id',
        string='Ticket',
        readonly=True
    )
    tagged_user_id = fields.Many2one(
        'res.users',
        related='tag_transfer_id.tagged_user_id',
        string='Tagged User',
        readonly=True
    )
    date_tagged = fields.Datetime(
        related='tag_transfer_id.date_tagged',
        string='Date Tagged',
        readonly=True
    )
    estimated_resolution_time = fields.Float(
        string='Estimated Resolution Time (Hours)',
        compute='_compute_estimated_resolution_time',
        help='Time from when you were tagged until now'
    )
    closing_notes = fields.Text(
        string='Closing Notes',
        help='Optional notes about the completion of this assignment'
    )
    work_summary = fields.Text(
        string='Work Summary',
        help='Brief summary of work done on this assignment',
        placeholder='Describe what you did to complete this assignment...'
    )
    
    @api.depends('date_tagged')
    def _compute_estimated_resolution_time(self):
        for record in self:
            if record.date_tagged:
                now = fields.Datetime.now()
                delta = now - record.date_tagged
                record.estimated_resolution_time = delta.total_seconds() / 3600
            else:
                record.estimated_resolution_time = 0.0

    def action_confirm_close(self):
        """Confirm and close the assignment"""
        self.ensure_one()
        now = fields.Datetime.now()
        
        # Update the tag transfer record
        self.tag_transfer_id.write({
            'action': 'closed',
            'closed_at': now
        })
        
        # Prepare message body
        resolution_hours = self.tag_transfer_id.resolution_time
        
        # Convert to days, hours, minutes, seconds
        total_seconds = resolution_hours * 3600
        days = int(total_seconds // 86400)
        remaining_seconds = total_seconds % 86400
        hours = int(remaining_seconds // 3600)
        remaining_seconds = remaining_seconds % 3600
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)
        
        # Build time string
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            time_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            time_parts.append(f"{minutes} min{'s' if minutes != 1 else ''}")
        if seconds > 0 or len(time_parts) == 0:
            time_parts.append(f"{seconds} sec{'s' if seconds != 1 else ''}")
        
        time_string = ", ".join(time_parts)
        
        message_body = Markup("""
            <div style="padding: 10px; background-color: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px;">
                <h4 style="color: #155724; margin-top: 0;">✅ Assignment Closed</h4>
                <p><b>{tagged}</b> completed the tag assignment from <b>{by}</b></p>
                <p><b>Closed At:</b> {closed_at}</p>
                <p><b>Resolution Time:</b> {time_string}</p>
        """).format(
            tagged=self.tagged_user_id.name,
            by=self.tag_transfer_id.tagged_by_user_id.name,
            closed_at=now.strftime('%Y-%m-%d %H:%M:%S'),
            time_string=time_string,
        )
        
        # Add work summary if provided
        if self.work_summary:
            message_body += Markup("""
                <hr style="border-color: #c3e6cb;"/>
                <p><b>Work Summary:</b></p>
                <p style="margin-left: 15px;">{summary}</p>
            """).format(summary=self.work_summary)
        
        # Add closing notes if provided
        if self.closing_notes:
            message_body += Markup("""
                <p><b>Notes:</b></p>
                <p style="margin-left: 15px;">{notes}</p>
            """).format(notes=self.closing_notes)
        
        message_body += Markup("</div>")
        
        # Post message to ticket
        self.ticket_id.message_post(
            body=message_body,
            subtype_xmlid="mail.mt_note"
        )
        
        # Show success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Assignment Closed Successfully!',
                'message': f'Resolution time: {resolution_hours:.2f} hours',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
