from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _
from datetime import datetime, timedelta
from odoo.tools import html2plaintext
from markupsafe import Markup, escape
import math

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'
    
    stage_id = fields.Many2one(
        'helpdesk.stage',
        string='Stage',
           domain="[('name', '!=', 'New')]",
    )
    reason_description_to_hold_ticket = fields.Text(string='Reason to Hold Ticket')
    common_reasons_to_hold_ticket =  fields.Many2many(
        'helpdesk.hold.reason',
        string='Common Reasons to Hold Ticket'
    )
    sla_description = fields.Html(string='SLA Description', compute="_compute_sla_description")
    transfer_ids = fields.One2many('helpdesk.ticket.transfer', 'ticket_id', string='Ticket Transfers History')
    tag_transfer_ids = fields.One2many(
        'helpdesk.ticket.tag.transfer', 
        'ticket_id', 
        string='Tag Transfer Lines',
        help='Users tagged in chatter and their responses'
    )
    sla_breached = fields.Boolean(string="SLA Breached", default=False)
    sla_breach_time = fields.Datetime(string="SLA Breach Time")
    sla_status = fields.Selection([
        ('safe', 'Safe - Within SLA'),
        ('warning', 'Warning - Approaching SLA'),
        ('critical', 'Critical - Near Breach'),
        ('breached', 'Breached - SLA Exceeded'),
        ('paused', 'Paused - On Hold')
    ], string="SLA Status", compute='_compute_sla_status', store=True)
    sla_warning_sent = fields.Boolean(string="SLA Warning Sent", default=False)
    sla_critical_sent = fields.Boolean(string="SLA Critical Sent", default=False)
    is_on_hold = fields.Boolean(compute='_compute_is_on_hold', store=True)
    working_time_config_id = fields.Many2one(
        'helpdesk.working.time', 
        string='Working Time Configuration',
        help='Select working time configuration for SLA calculations'
    )
    business_hours_spent = fields.Float(
        string='Business Hours Spent', 
        compute='_compute_business_hours_spent',
        store=True,
        help='Time spent in business hours only'
    )
    sla_remaining_hours = fields.Float(
        string='SLA Remaining Hours',
        compute='_compute_sla_remaining_hours',
        store=True,
        help='Remaining SLA hours considering working time'
    )
    hold_time_logs = fields.One2many(
        'helpdesk.ticket.hold.log',
        'ticket_id',
        string='Hold Time Logs',
        help='Track when ticket was put on hold and resumed'
    )
    total_hold_time_hours = fields.Float(
        string='Total Hold Time (Hours)',
        compute='_compute_total_hold_time',
        store=True,
        help='Total time spent in hold status'
    )
    sla_team_tag_domain = fields.Char(
        string='SLA Tag Domain',
        compute='_compute_sla_team_tag_ids',
        help='Odoo domain string restricting tags to those in team SLA policies'
    )

    @api.depends('team_id')
    def _compute_sla_team_tag_ids(self):
        for ticket in self:
            if ticket.team_id:
                sla_policies = self.env['helpdesk.sla'].search([
                    ('team_id', '=', ticket.team_id.id),
                    ('tag_ids', '!=', False),
                ])
                tag_ids = sla_policies.mapped('tag_ids').ids
                if tag_ids:
                    ticket.sla_team_tag_domain = "[('id', 'in', %s)]" % str(tag_ids)
                else:
                    ticket.sla_team_tag_domain = "[('id', 'in', [])]"
            else:
                ticket.sla_team_tag_domain = "[]"

    @api.depends('team_id')
    def _compute_domain_user_ids(self):
        """Override: restrict Assigned To to members of the selected team only."""
        for ticket in self:
            if ticket.team_id and ticket.team_id.member_ids:
                ticket.domain_user_ids = ticket.team_id.member_ids
            else:
                # Fallback: all helpdesk users when no team selected
                user_ids = self.env.ref('helpdesk.group_helpdesk_user').all_user_ids
                ticket.domain_user_ids = user_ids

    @api.onchange('team_id')
    def _onchange_team_id_clear_stale(self):
        """Clear user_id and tag_ids if they no longer belong to the new team."""
        if self.team_id:
            # Clear user_id if not a member of the new team
            if self.user_id and self.user_id not in self.team_id.member_ids:
                self.user_id = False
            # Clear tags not linked to any SLA policy of the new team
            if self.tag_ids:
                sla_policies = self.env['helpdesk.sla'].search([
                    ('team_id', '=', self.team_id.id),
                    ('tag_ids', '!=', False),
                ])
                valid_tag_ids = sla_policies.mapped('tag_ids').ids
                self.tag_ids = self.tag_ids.filtered(lambda t: t.id in valid_tag_ids)

    @api.depends('stage_id')
    def _compute_is_on_hold(self):
        for rec in self:
            rec.is_on_hold = rec.stage_id.name == 'On Hold'
            
    @api.depends('hold_time_logs.duration_hours')
    def _compute_total_hold_time(self):
        for ticket in self:
            ticket.total_hold_time_hours = sum(ticket.hold_time_logs.mapped('duration_hours'))
            
    def _get_adjusted_sla_deadline(self):
        """Calculate SLA deadline adjusted for hold time"""
        if not self.sla_deadline:
            return fields.Datetime.now()
            
        # Add total hold time to the original deadline
        adjusted_deadline = self.sla_deadline + timedelta(hours=self.total_hold_time_hours)
        
        # If ticket is currently on hold, add the current hold duration
        if self.is_on_hold:
            current_hold_log = self.hold_time_logs.filtered(lambda log: not log.end_time)
            if current_hold_log:
                current_hold_duration = (fields.Datetime.now() - current_hold_log.start_time).total_seconds() / 3600
                adjusted_deadline += timedelta(hours=current_hold_duration)
                
        return adjusted_deadline
        
    def _create_hold_log(self):
        """Create a new hold log when ticket is put on hold"""
        self.env['helpdesk.ticket.hold.log'].create({
            'ticket_id': self.id,
            'start_time': fields.Datetime.now(),
            'reason': ', '.join(self.common_reasons_to_hold_ticket.mapped('name')) if self.common_reasons_to_hold_ticket else 'No reason specified'
        })
        
        # Post SLA pause notification
        self.message_post(
            body=Markup(
                "<div class='alert alert-info'>"
                "<h5><i class='fa fa-pause-circle text-warning'></i> SLA Timer Paused</h5>"
                "<p>Ticket has been put on hold. SLA counting is now <strong>paused</strong> until the ticket is resumed.</p>"
                "<p><small class='text-muted'>Hold started at: {ts}</small></p>"
                "</div>"
            ).format(ts=fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            subtype_xmlid="mail.mt_note"
        )
        
    def _end_hold_log(self):
        """End the current hold log when ticket is removed from hold"""
        current_hold_log = self.hold_time_logs.filtered(lambda log: not log.end_time)
        if current_hold_log:
            end_time = fields.Datetime.now()
            current_hold_log.write({
                'end_time': end_time
            })
            
            # Calculate hold duration for the message
            duration_hours = (end_time - current_hold_log.start_time).total_seconds() / 3600
            
            # Post SLA resume notification
            self.message_post(
                body=Markup(
                    "<div class='alert alert-success'>"
                    "<h5><i class='fa fa-play-circle text-success'></i> SLA Timer Resumed</h5>"
                    "<p>Ticket has been removed from hold. SLA counting has <strong>resumed</strong>.</p>"
                    "<p><strong>Hold Duration:</strong> {hours:.2f} hours</p>"
                    "<p><small class='text-muted'>Resumed at: {ts}</small></p>"
                    "</div>"
                ).format(hours=duration_hours, ts=end_time.strftime('%Y-%m-%d %H:%M:%S')),
                subtype_xmlid="mail.mt_note"
            )
    




    @api.depends('sla_deadline', 'sla_breached', 'stage_id', 'is_on_hold')
    def _compute_sla_status(self):
        """Compute SLA status based on deadline proximity (paused when on hold)"""
        now = fields.Datetime.now()
        
        for ticket in self:
            if not ticket.sla_deadline or ticket.stage_id.fold:  # Closed tickets
                ticket.sla_status = 'safe'
                continue
                
            # If ticket is on hold, SLA is paused - show paused status
            if ticket.is_on_hold:
                ticket.sla_status = 'paused'
                continue
                
            if ticket.sla_breached:
                ticket.sla_status = 'breached'
                continue
                
            # Calculate adjusted deadline (excluding hold time)
            adjusted_deadline = ticket._get_adjusted_sla_deadline()
            time_left = adjusted_deadline - now
            total_hours = time_left.total_seconds() / 3600
            
            if total_hours <= 0:
                ticket.sla_status = 'breached'
            elif total_hours <= 2:  # Less than 2 hours
                ticket.sla_status = 'critical'
            elif total_hours <= 24:  # Less than 24 hours
                ticket.sla_status = 'warning'
            else:
                ticket.sla_status = 'safe'

    @api.depends('create_date', 'working_time_config_id', 'stage_id', 'total_hold_time_hours')
    def _compute_business_hours_spent(self):
        for ticket in self:
            if not ticket.working_time_config_id or not ticket.create_date:
                ticket.business_hours_spent = 0.0
                continue
            
            current_time = fields.Datetime.now()
            if ticket.stage_id.fold:  # If ticket is closed
                # Use close date if available, otherwise current time
                end_time = ticket.write_date or current_time
            else:
                end_time = current_time
                
            total_elapsed_hours = ticket._calculate_business_hours(
                ticket.create_date, end_time
            )
            
            # Subtract hold time from business hours
            ticket.business_hours_spent = max(0.0, total_elapsed_hours - ticket.total_hold_time_hours)

    @api.depends('sla_deadline', 'business_hours_spent', 'working_time_config_id', 'total_hold_time_hours')
    def _compute_sla_remaining_hours(self):
        for ticket in self:
            if not ticket.sla_deadline or not ticket.working_time_config_id:
                ticket.sla_remaining_hours = 0.0
                continue
                
            current_time = fields.Datetime.now()
            
            # Get adjusted deadline considering hold time
            adjusted_deadline = ticket._get_adjusted_sla_deadline()
            
            if current_time >= adjusted_deadline:
                ticket.sla_remaining_hours = 0.0
            else:
                remaining_business_hours = ticket._calculate_business_hours(
                    current_time, adjusted_deadline
                )
                ticket.sla_remaining_hours = remaining_business_hours

    @api.constrains('stage_id', 'common_reasons_to_hold_ticket')
    def _check_hold_reason_required(self):
        """Validate that hold reasons are provided when moving to On Hold stage"""
        for record in self:
            if record.stage_id.name == 'On Hold':
                if not record.common_reasons_to_hold_ticket:
                    raise ValidationError(
                        _("🚫 Hold Reason Required\n\n"
                          "You cannot move this ticket to 'On Hold' status without selecting a valid reason.\n\n"
                          "Required Actions:\n"
                          "1. Select at least one reason from 'Hold Reasons' checkboxes\n"
                          "2. Optionally provide additional details in the description field\n"
                          "3. Try changing the stage again\n\n"
                          "This ensures proper tracking and reporting of hold reasons for better ticket management.")
                    )

    def write(self, vals):
        """Override write method to handle stage changes, SLA updates, and hold tracking"""
        # Track hold status changes
        old_hold_status = {}
        if 'stage_id' in vals:
            new_stage = self.env['helpdesk.stage'].browse(vals['stage_id'])
            for record in self:
                old_hold_status[record.id] = {
                    'was_on_hold': record.is_on_hold,
                    'is_going_on_hold': new_stage.name == 'On Hold'
                }
        
        # Store old values for comparison
        old_values = {}
        if 'sla_deadline' in vals or 'user_id' in vals or 'team_id' in vals:
            for record in self:
                old_values[record.id] = {
                    'sla_deadline': record.sla_deadline,
                    'user_id': record.user_id,
                    'team_id': record.team_id
                }
        
        # Check if stage is being changed to "On Hold"
        if 'stage_id' in vals:
            new_stage = self.env['helpdesk.stage'].browse(vals['stage_id'])
            if new_stage.name == 'On Hold':
                for record in self:
                    # Check if common_reasons_to_hold_ticket is being set in this write
                    hold_reasons = vals.get('common_reasons_to_hold_ticket', record.common_reasons_to_hold_ticket)
                    
                    # If no hold reasons are provided, prevent the stage change
                    if not hold_reasons or (isinstance(hold_reasons, list) and not any(hold_reasons)):
                        raise ValidationError(
                            _("🚫 Cannot Move to On Hold Status\n\n"
                              "Ticket: %s\n\n"
                              "Before moving this ticket to 'On Hold', you must:\n"
                              "✓ Select at least one hold reason from the available options\n"
                              "✓ Optionally provide additional context in the details field\n\n"
                              "This requirement ensures proper documentation and tracking of hold reasons "
                              "for reporting and ticket management purposes.") % record.name
                        )
        
        # Execute the write
        result = super(HelpdeskTicket, self).write(vals)
        
        # Handle hold status changes after write
        if 'stage_id' in vals:
            for record in self:
                old_status = old_hold_status.get(record.id, {})
                was_on_hold = old_status.get('was_on_hold', False)
                is_now_on_hold = record.is_on_hold
                
                if not was_on_hold and is_now_on_hold:
                    # Ticket put on hold - create hold log and immediately pause SLA
                    record._create_hold_log()
                    # Force immediate SLA status update to 'paused'
                    record._compute_sla_status()
                elif was_on_hold and not is_now_on_hold:
                    # Ticket removed from hold - end hold log and resume SLA
                    record._end_hold_log()
                    # Force immediate SLA status recalculation
                    record._compute_sla_status()
        
        # Check for SLA-related changes and send notifications
        if 'sla_deadline' in vals or 'user_id' in vals or 'team_id' in vals:
            self._handle_sla_updates(old_values, vals)
        
        return result

    def _handle_sla_updates(self, old_values, new_vals):
        """Handle SLA updates and send notifications to stakeholders"""
        for record in self:
            old_data = old_values.get(record.id, {})
            changes = []
            
            # Check what changed
            if 'sla_deadline' in new_vals and old_data.get('sla_deadline') != record.sla_deadline:
                old_deadline = old_data.get('sla_deadline')
                changes.append(f"SLA Deadline: {old_deadline.strftime('%Y-%m-%d %H:%M') if old_deadline else 'None'} → {record.sla_deadline.strftime('%Y-%m-%d %H:%M') if record.sla_deadline else 'None'}")
                
            if 'user_id' in new_vals and old_data.get('user_id') != record.user_id:
                old_user = old_data.get('user_id')
                changes.append(f"Assigned To: {record.user_id.name if record.user_id else 'Unassigned'}  ")
                
            if 'team_id' in new_vals and old_data.get('team_id') != record.team_id:
                old_team = old_data.get('team_id')
                changes.append(f"Team: {old_team.name if old_team else 'None'} → {record.team_id.name if record.team_id else 'None'}")
            
            # Send notification if there are relevant changes
            if changes:
                record._send_sla_update_notification(changes)

    def _get_sla_notification_recipients(self):
        """Return a recordset of res.users who should be notified for these tickets.
        
        ONLY sends notifications to followers of the ticket (internal users).
        """
        recipients = self.env['res.users']
        for ticket in self:
            users = self.env['res.users']
            
            # Get ticket followers who are internal users
            follower_users = ticket.message_follower_ids.mapped('partner_id.user_ids').filtered(
                lambda u: u.has_group('base.group_user')
            )
            users |= follower_users
            
            # Add collected users to recipients
            recipients |= users
            
        return recipients.filtered(lambda u: u.active)

    
    
    def _send_sla_breach_notifications(self):
        """Post SLA breach message in chatter (email notifications disabled)"""
        recipients = self._get_sla_notification_recipients()
        
        # Create notification message in chatter only
        self.message_post(
            body=Markup(
                "<div class='alert alert-danger'>"
                "<h5><i class='fa fa-exclamation-triangle'></i> SLA Breach Alert</h5>"
                "<p><strong>This ticket has exceeded its SLA deadline!</strong></p>"
                "<ul>"
                "<li><strong>Deadline:</strong> {deadline}</li>"
                "<li><strong>Breach Time:</strong> {breach}</li>"
                "<li><strong>Priority:</strong> {priority}</li>"
                "<li><strong>Stage:</strong> {stage}</li>"
                "</ul>"
                "</div>"
            ).format(
                deadline=self.sla_deadline.strftime('%Y-%m-%d %H:%M:%S') if self.sla_deadline else 'Not Set',
                breach=self.sla_breach_time.strftime('%Y-%m-%d %H:%M:%S') if self.sla_breach_time else fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                priority=escape(dict(self._fields['priority'].selection).get(self.priority, 'Normal')),
                stage=escape(self.stage_id.name or 'Unknown'),
            ),
            subtype_xmlid="mail.mt_comment",
            partner_ids=recipients.mapped('partner_id').ids
        )

    def _send_sla_warning_notification(self, warning_type='warning'):
        """Send SLA warning notifications (warning or critical) considering hold time"""
        if warning_type == 'warning' and self.sla_warning_sent:
            return  # Already sent
        elif warning_type == 'critical' and self.sla_critical_sent:
            return  # Already sent
            
        recipients = self._get_sla_notification_recipients()
        
        # Calculate time remaining with adjusted deadline
        now = fields.Datetime.now()
        adjusted_deadline = self._get_adjusted_sla_deadline()
        time_left = adjusted_deadline - now if adjusted_deadline else None
        hours_left = time_left.total_seconds() / 3600 if time_left else 0
        
        # Determine message and urgency
        if warning_type == 'critical':
            icon = '🔴'
            urgency = 'CRITICAL'
            bg_color = '#dc3545'
            message_type = 'Critical SLA Alert'
        else:
            icon = '🟡'
            urgency = 'WARNING'
            bg_color = '#ffc107'
            message_type = 'SLA Warning'
            
        # Post message in chatter
        self.message_post(
            body=Markup(
                "<div class='alert alert-warning'>"
                "<h5>{icon} {msg_type}: SLA Deadline Approaching</h5>"
                "<p><strong>Time remaining:</strong> {hours:.1f} hours</p>"
                "<p><strong>Adjusted Deadline:</strong> {deadline}</p>"
                "<p><strong>Hold Time Excluded:</strong> {hold:.1f} hours</p>"
                "<p><em>Team members have been notified.</em></p>"
                "</div>"
            ).format(
                icon=icon,
                msg_type=message_type,
                hours=hours_left,
                deadline=adjusted_deadline.strftime('%Y-%m-%d %H:%M:%S') if adjusted_deadline else 'Not Set',
                hold=self.total_hold_time_hours,
            ),
            subtype_xmlid="mail.mt_comment",
            partner_ids=recipients.mapped('partner_id').ids
        )
        
        # Send email notifications - DISABLED to keep notifications within Odoo only
        # Email notifications are disabled - all notifications handled via chatter
        pass
        
        # Mark as sent
        if warning_type == 'warning':
            self.sla_warning_sent = True
        else:
            self.sla_critical_sent = True

    def _send_sla_update_notification(self, changes):
        """Send notification when SLA-related information is updated"""
        recipients = self._get_sla_notification_recipients()
        
        # Post message in chatter
        changes_html = Markup("<br/>").join(Markup("• {c}").format(c=escape(change)) for change in changes)
        self.message_post(
            body=Markup(
                "<div class='alert alert-info'>"
                "<h5><i class='fa fa-info-circle'></i> SLA Information Updated</h5>"
                "<p><strong>The following changes were made:</strong></p>"
                "<p>{changes}</p>"
                "<p><em>Relevant team members have been notified.</em></p>"
                "</div>"
            ).format(changes=changes_html),
            subtype_xmlid="mail.mt_comment",
            partner_ids=recipients.mapped('partner_id').ids
        )
        
        # Send email notifications to stakeholders - DISABLED to keep notifications within Odoo only
        # Email notifications are disabled - all notifications handled via chatter
        pass

    @api.model
    def _check_sla_status_updates(self):
        """Check for SLA status changes and send appropriate notifications"""
        now = fields.Datetime.now()
        
        # Find tickets approaching SLA deadlines
        warning_tickets = self.search([
            ('sla_deadline', '>', now),
            ('sla_deadline', '<=', now + timedelta(hours=24)),
            ('sla_warning_sent', '=', False),
            ('stage_id.fold', '=', False),
            ('sla_breached', '=', False)
        ])
        
        critical_tickets = self.search([
            ('sla_deadline', '>', now),
            ('sla_deadline', '<=', now + timedelta(hours=2)),
            ('sla_critical_sent', '=', False),
            ('stage_id.fold', '=', False),
            ('sla_breached', '=', False)
        ])
        
        # Send warning notifications
        for ticket in warning_tickets:
            ticket._send_sla_warning_notification('warning')
            
        # Send critical notifications
        for ticket in critical_tickets:
            ticket._send_sla_warning_notification('critical')

    @api.model
    def _check_sla_breaches(self):
        """Check for SLA breaches considering hold time (hold tickets are excluded)"""
        now = fields.Datetime.now()
        
        # Find tickets that have breached SLA (excluding hold tickets)
        breached_tickets = self.search([
            ('sla_deadline', '<', now),
            ('sla_breached', '=', False),
            ('stage_id.fold', '=', False),  # Only active stages
            ('is_on_hold', '=', False)  # Exclude tickets on hold
        ])
        
        # For each ticket, check if it's really breached considering hold time
        truly_breached = self.env['helpdesk.ticket']
        for ticket in breached_tickets:
            adjusted_deadline = ticket._get_adjusted_sla_deadline()
            if now >= adjusted_deadline:
                truly_breached |= ticket
        
        # Mark as breached and post chatter message
        for ticket in truly_breached:
            ticket.write({
                'sla_breached': True,
                'sla_breach_time': now
            })
            
            # Post breach notification in chatter (no email)
            ticket._send_sla_breach_notifications()

    def _calculate_business_hours(self, start_datetime, end_datetime):
        """Calculate business hours between two datetime objects based on working time configuration"""
        if not self.working_time_config_id or not start_datetime or not end_datetime:
            return 0.0
            
        # Get all working time configurations (for all days of the week)
        working_times = self.env['helpdesk.working.time'].search([
            ('company_id', '=', self.company_id.id or self.env.company.id),
            ('active', '=', True)
        ])
        
        if not working_times:
            return 0.0
            
        total_hours = 0.0
        current_date = start_datetime.date()
        end_date = end_datetime.date()
        
        while current_date <= end_date:
            day_of_week = str(current_date.weekday())  # Monday = 0, Sunday = 6
            
            # Find working time for this day
            working_time = working_times.filtered(lambda w: w.day_of_week == day_of_week)
            if not working_time:
                current_date += timedelta(days=1)
                continue
                
            working_time = working_time[0]  # Take the first one
            
            # Calculate working hours for this day
            day_start = datetime.combine(current_date, datetime.min.time()) + timedelta(hours=working_time.hour_from)
            day_end = datetime.combine(current_date, datetime.min.time()) + timedelta(hours=working_time.hour_to)
            
            # Adjust for start and end times
            if current_date == start_datetime.date():
                day_start = max(day_start, start_datetime.replace(tzinfo=None))
            if current_date == end_datetime.date():
                day_end = min(day_end, end_datetime.replace(tzinfo=None))
                
            if day_start < day_end:
                day_hours = (day_end - day_start).total_seconds() / 3600
                total_hours += day_hours
                
            current_date += timedelta(days=1)
            
        return total_hours

    def _calculate_sla_deadline_with_working_time(self, sla_hours):
        """Calculate SLA deadline considering only working time"""
        if not self.working_time_config_id or not sla_hours:
            return fields.Datetime.now() + timedelta(hours=sla_hours)
            
        working_times = self.env['helpdesk.working.time'].search([
            ('company_id', '=', self.company_id.id or self.env.company.id),
            ('active', '=', True)
        ])
        
        if not working_times:
            return fields.Datetime.now() + timedelta(hours=sla_hours)
            
        remaining_hours = sla_hours
        current_datetime = self.create_date or fields.Datetime.now()
        
        while remaining_hours > 0:
            current_date = current_datetime.date()
            day_of_week = str(current_date.weekday())
            
            working_time = working_times.filtered(lambda w: w.day_of_week == day_of_week)
            if not working_time:
                # No working time for this day, move to next day
                current_datetime = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
                continue
                
            working_time = working_time[0]
            day_start = datetime.combine(current_date, datetime.min.time()) + timedelta(hours=working_time.hour_from)
            day_end = datetime.combine(current_date, datetime.min.time()) + timedelta(hours=working_time.hour_to)
            
            # If current time is before work start, move to work start
            if current_datetime.replace(tzinfo=None) < day_start:
                current_datetime = day_start
                
            # If current time is after work end, move to next day
            if current_datetime.replace(tzinfo=None) >= day_end:
                current_datetime = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
                continue
                
            # Calculate available hours in this working day
            available_hours = (day_end - current_datetime.replace(tzinfo=None)).total_seconds() / 3600
            
            if remaining_hours <= available_hours:
                # SLA deadline is within this working day
                return current_datetime + timedelta(hours=remaining_hours)
            else:
                # Use all available hours and continue to next working day
                remaining_hours -= available_hours
                current_datetime = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
                
        return current_datetime

   

    @api.depends('sla_ids')
    def _compute_sla_description(self):
        for ticket in self:
            sla = ticket.sla_ids[:1]
            ticket.sla_description = sla.description if sla else ''
            
    @api.model
    def create(self, vals):
        """Override create to set working time configuration and calculate SLA with working time"""
        ticket = super(HelpdeskTicket, self).create(vals)
        
        # Set default working time configuration if not provided
        if not ticket.working_time_config_id:
            default_working_time = self.env['helpdesk.working.time'].search([
                ('company_id', '=', ticket.company_id.id or self.env.company.id),
                ('active', '=', True)
            ], limit=1)
            if default_working_time:
                ticket.working_time_config_id = default_working_time.id
        
        # Recalculate SLA deadline with working time
        if ticket.working_time_config_id and hasattr(ticket, 'sla_deadline') and ticket.sla_ids:
            ticket._recalculate_sla_with_working_time()
            
        return ticket
    
    def _recalculate_sla_with_working_time(self):
        """Recalculate SLA deadline considering working time configuration"""
        if not self.working_time_config_id:
            return
            
        # Get SLA policy for this ticket
        sla_policy = self.sla_ids[:1]
        
        if sla_policy and hasattr(sla_policy, 'time') and sla_policy.time:
            # Calculate new SLA deadline based on working time
            new_deadline = self._calculate_sla_deadline_with_working_time(sla_policy.time)
            self.sla_deadline = new_deadline
    
    def action_assign_working_time(self):
        """Action to manually assign or change working time configuration"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Select Working Time Configuration',
            'res_model': 'helpdesk.working.time',
            'view_mode': 'list,form',
            'target': 'new',
            'domain': [('company_id', '=', self.company_id.id or self.env.company.id)],
            'context': {
                'default_company_id': self.company_id.id or self.env.company.id,
                'ticket_id': self.id,
            }
        }
    
    def message_post(self, **kwargs):
        """Override message_post to detect @user mentions and create transfer lines.
        Also disable all email notifications to keep everything within Odoo."""
        
        # DISABLE EMAIL NOTIFICATIONS via context flags (Odoo 19 compatible)
        # Remove unsupported kwargs if present
        kwargs.pop('email_to', None)
        kwargs.pop('email_from', None)
        
        # Disable email notifications by setting email context
        context = self.env.context.copy()
        context.update({
            'mail_create_nosubscribe': True,  # Don't auto-subscribe
            'mail_create_nolog': False,       # Still log messages
            'mail_notrack': False,            # Still track changes
            'mail_notify_author': False,      # Don't notify author
            'mail_post_autofollow': True,     # Still follow for chatter
            'no_reset_password': True,        # Don't send reset password emails
        })
        
        # Note: subtype_xmlid is left as-is to preserve mt_comment vs mt_note
        # (forcing mt_note was causing SLA notification messages to be wrongly downgraded)

        import re
        import logging
        
        _logger = logging.getLogger(__name__)
        
        # Call parent method with disabled email context
        message = super(HelpdeskTicket, self.with_context(context)).message_post(**kwargs)
        
        # Check if body contains user mentions
        body = kwargs.get('body', '')
        _logger.info(f"DEBUG: message_post called for ticket {self.id}, body: {body}")
        
        if body and '@' in body:
            mentioned_user_ids = []
            
            # Method 1: Extract mentioned user IDs from Odoo HTML format (when using @ mention dropdown)
            mention_pattern = r'data-oe-id="(\d+)"[^>]*data-oe-model="res\.users"'
            html_mentioned_ids = re.findall(mention_pattern, body)
            mentioned_user_ids.extend(html_mentioned_ids)
            _logger.info(f"DEBUG: HTML mentions found: {html_mentioned_ids}")
            
            # Method 2: Extract simple @username mentions from plain text
            try:
                
                plain_body = html2plaintext(body) if body else ''
            except:
                # Fallback: simple HTML tag removal
                plain_body = re.sub(r'<[^>]*>', '', body)
            
            username_pattern = r'@(\w+)'
            usernames = re.findall(username_pattern, plain_body)
            _logger.info(f"DEBUG: Plain text mentions found: {usernames}")
            
            if usernames:
                # Look up users by login name or name
                for username in usernames:
                    # Try by login first
                    user = self.env['res.users'].search([('login', '=', username)], limit=1)
                    if not user:
                        # Try by name (case insensitive)
                        user = self.env['res.users'].search([('name', 'ilike', username)], limit=1)
                    if user:
                        mentioned_user_ids.append(str(user.id))
                        _logger.info(f"DEBUG: Found user {user.name} (ID: {user.id}) for mention @{username}")
            
            # Method 3: Check if there are partner mentions in the message
            if hasattr(message, 'partner_ids') and message.partner_ids:
                for partner in message.partner_ids:
                    user = self.env['res.users'].search([('partner_id', '=', partner.id)], limit=1)
                    if user:
                        mentioned_user_ids.append(str(user.id))
                        _logger.info(f"DEBUG: Found user from partner_ids: {user.name} (ID: {user.id})")
            
            if mentioned_user_ids:
                # Get the user who posted the message
                author_id = kwargs.get('author_id') or self.env.user.partner_id.id
                author_user = self.env['res.users'].search([('partner_id', '=', author_id)], limit=1)
                
                if not author_user:
                    author_user = self.env.user
                
                _logger.info(f"DEBUG: Author user: {author_user.name} (ID: {author_user.id})")
                
                # Remove duplicates
                mentioned_user_ids = list(set(mentioned_user_ids))
                
                for user_id in mentioned_user_ids:
                    try:
                        user_id = int(user_id)
                        # Don't create transfer for self-mentions
                        if user_id != author_user.id:
                            # Check if transfer already exists for this ticket and user (not message specific)
                            existing = self.env['helpdesk.ticket.tag.transfer'].search([
                                ('ticket_id', '=', self.id),
                                ('tagged_user_id', '=', user_id),
                                ('action', '=', 'pending')
                            ])
                            if not existing:
                                transfer = self.env['helpdesk.ticket.tag.transfer'].create_transfer_from_mention(
                                    ticket_id=self.id,
                                    tagged_user_id=user_id,
                                    tagged_by_user_id=author_user.id,
                                    message_id=message.id
                                )
                                _logger.info(f"DEBUG: Created transfer record {transfer.id} for user {user_id}")
                            else:
                                _logger.info(f"DEBUG: Transfer already exists for user {user_id}")
                    except (ValueError, TypeError) as e:
                        _logger.error(f"DEBUG: Error processing user_id {user_id}: {e}")
                        continue
            else:
                _logger.info("DEBUG: No mentioned users found")
        else:
            _logger.info("DEBUG: No @ symbol in body or no body")
        
        return message

    def action_test_tagging(self):
        """Test method to create a tag assignment for debugging"""
        transfer = self.env['helpdesk.ticket.tag.transfer'].test_create_transfer(self.id)
        if transfer:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Test Tag Created',
                    'message': f'Created test tag assignment: {transfer.tagged_user_id.name} tagged by {transfer.tagged_by_user_id.name}',
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Test Failed',
                    'message': 'Could not create test tag assignment',
                    'type': 'warning',
                }
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
            self.write({'stage_id': in_progress_stage.id})
            
            # Update any tag transfer records that are on hold to in_progress
            hold_transfers = self.tag_transfer_ids.filtered(lambda t: t.action == 'hold')
            if hold_transfers:
                hold_transfers.write({'action': 'in_progress'})
            
            # End any active hold logs
            active_hold_logs = self.hold_time_logs.filtered(lambda log: not log.end_time)
            if active_hold_logs:
                now = fields.Datetime.now()
                active_hold_logs.write({'end_time': now})
                
                # Recompute hold time
                self._compute_total_hold_time()
                
                # Recalculate SLA status
                self._compute_sla_status()
                
            # Post a message
            self.message_post(
                body=Markup("⏯️ Ticket removed from hold by <b>{user}</b>. SLA timer resumed.").format(
                    user=self.env.user.name,
                ),
                subtype_xmlid="mail.mt_note"
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Ticket has been removed from hold and SLA timer resumed.',
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': 'Could not find In Progress stage to move ticket to.',
                    'type': 'warning',
                    'sticky': False,
                }
            }
