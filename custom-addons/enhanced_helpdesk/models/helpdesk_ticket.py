from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _
from datetime import datetime, timedelta
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
        'helpdesk.ticket.hold.reason',
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
        ('breached', 'Breached - SLA Exceeded')
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

    @api.depends('stage_id')
    def _compute_is_on_hold(self):
        for rec in self:
            rec.is_on_hold = rec.stage_id.name == 'On Hold'

    @api.depends('sla_deadline', 'sla_breached', 'stage_id')
    def _compute_sla_status(self):
        """Compute SLA status based on deadline proximity"""
        now = fields.Datetime.now()
        
        for ticket in self:
            if not ticket.sla_deadline or ticket.stage_id.fold:  # Closed tickets
                ticket.sla_status = 'safe'
                continue
                
            if ticket.sla_breached:
                ticket.sla_status = 'breached'
                continue
                
            time_left = ticket.sla_deadline - now
            total_hours = time_left.total_seconds() / 3600
            
            if total_hours <= 0:
                ticket.sla_status = 'breached'
            elif total_hours <= 2:  # Less than 2 hours
                ticket.sla_status = 'critical'
            elif total_hours <= 24:  # Less than 24 hours
                ticket.sla_status = 'warning'
            else:
                ticket.sla_status = 'safe'

    @api.depends('create_date', 'working_time_config_id', 'stage_id')
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
                
            ticket.business_hours_spent = ticket._calculate_business_hours(
                ticket.create_date, end_time
            )

    @api.depends('sla_deadline', 'business_hours_spent', 'working_time_config_id')
    def _compute_sla_remaining_hours(self):
        for ticket in self:
            if not ticket.sla_deadline or not ticket.working_time_config_id:
                ticket.sla_remaining_hours = 0.0
                continue
                
            current_time = fields.Datetime.now()
            if current_time >= ticket.sla_deadline:
                ticket.sla_remaining_hours = 0.0
            else:
                remaining_business_hours = ticket._calculate_business_hours(
                    current_time, ticket.sla_deadline
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
        """Override write method to handle stage changes and SLA updates"""
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
        """Return a recordset of res.users who should be notified for these tickets."""
        recipients = self.env['res.users']
        for ticket in self:
            users = self.env['res.users']
            # 1) Assigned user
            if getattr(ticket, 'user_id', False):
                users |= ticket.user_id
            # 2) Team leader/manager (robust lookup)
            team = getattr(ticket, 'team_id', False)
            if team:
                leader = False
                for candidate in ('user_id', 'leader_id', 'team_leader_id', 'manager_id'):
                    try:
                        leader = getattr(team, candidate, False) or False
                    except Exception:
                        leader = False
                    if leader:
                        users |= leader
                        break
                # 3) Team members if no specific assigned user
                if not getattr(ticket, 'user_id', False):
                    if hasattr(team, 'member_ids'):
                        users |= team.member_ids
                    elif hasattr(team, 'member_id'):
                        users |= team.member_id
            # 4) Ticket followers who are internal users
            follower_users = ticket.message_follower_ids.mapped('partner_id.user_ids').filtered(
                lambda u: u.has_group('base.group_user')
            )
            users |= follower_users
            # 5) Helpdesk managers (if group exists)
            try:
                managers = self.env.ref('helpdesk.group_helpdesk_manager').users.filtered(
                    lambda u: u.company_id == (ticket.company_id or self.env.company)
                )
                users |= managers
            except Exception:
                pass
            # 6) System administrators
            try:
                admins = self.env.ref('base.group_system').users.filtered(
                    lambda u: u.company_id == (ticket.company_id or self.env.company)
                )
                users |= admins
            except Exception:
                pass
            recipients |= users
        return recipients.filtered(lambda u: u.active)

    def _send_sla_breach_notifications(self):
        """Send SLA breach notification to all relevant stakeholders"""
        template = self.env.ref('enhanced_helpdesk.email_template_sla_breach', raise_if_not_found=False)
        if not template:
            return
            
        recipients = self._get_sla_notification_recipients()
        
        # Create notification message in chatter
        self.message_post(
            body=_(
                "<div class='alert alert-danger'>"
                "<h5><i class='fa fa-exclamation-triangle'></i> SLA Breach Alert</h5>"
                "<p><strong>This ticket has exceeded its SLA deadline!</strong></p>"
                "<ul>"
                "<li><strong>Deadline:</strong> %s</li>"
                "<li><strong>Breach Time:</strong> %s</li>"
                "<li><strong>Priority:</strong> %s</li>"
                "<li><strong>Stage:</strong> %s</li>"
                "</ul>"
                "<p><em>All relevant team members have been notified.</em></p>"
                "</div>"
            ) % (
                self.sla_deadline.strftime('%Y-%m-%d %H:%M:%S') if self.sla_deadline else 'Not Set',
                self.sla_breach_time.strftime('%Y-%m-%d %H:%M:%S') if self.sla_breach_time else fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                dict(self._fields['priority'].selection).get(self.priority, 'Normal'),
                self.stage_id.name or 'Unknown'
            ),
            subtype_xmlid="mail.mt_comment",  # Use comment to ensure visibility
            partner_ids=recipients.mapped('partner_id').ids
        )
        
        # Send individual emails to each recipient
        for recipient in recipients:
            try:
                template.with_context(
                    recipient_user=recipient,
                    lang=recipient.lang
                ).send_mail(
                    res_id=self.id,
                    email_values={
                        'email_to': recipient.email,
                        'recipient_ids': [(4, recipient.partner_id.id)]
                    },
                    force_send=True
                )
            except Exception as e:
                # Log error but continue with other notifications
                self.env['ir.logging'].create({
                    'name': 'SLA Breach Notification Error',
                    'type': 'server',
                    'level': 'error',
                    'message': f'Failed to send SLA breach notification to {recipient.name}: {str(e)}',
                    'path': 'enhanced_helpdesk.models.helpdesk_ticket',
                    'func': '_send_sla_breach_notifications'
                })

    def _send_sla_warning_notification(self, warning_type='warning'):
        """Send SLA warning notifications (warning or critical)"""
        if warning_type == 'warning' and self.sla_warning_sent:
            return  # Already sent
        elif warning_type == 'critical' and self.sla_critical_sent:
            return  # Already sent
            
        recipients = self._get_sla_notification_recipients()
        
        # Calculate time remaining
        now = fields.Datetime.now()
        time_left = self.sla_deadline - now if self.sla_deadline else None
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
            body=_(
                "<div class='alert alert-warning'>"
                "<h5>%s %s: SLA Deadline Approaching</h5>"
                "<p><strong>Time remaining:</strong> %.1f hours</p>"
                "<p><strong>Deadline:</strong> %s</p>"
                "<p><em>Team members have been notified.</em></p>"
                "</div>"
            ) % (
                icon, message_type,
                hours_left,
                self.sla_deadline.strftime('%Y-%m-%d %H:%M:%S') if self.sla_deadline else 'Not Set'
            ),
            subtype_xmlid="mail.mt_comment",
            partner_ids=recipients.mapped('partner_id').ids
        )
        
        # Send email notifications
        for recipient in recipients:
            try:
                self.env['mail.mail'].create({
                    'subject': f'{icon} {urgency}: SLA Alert - {self.name}',
                    'body_html': f'''
                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                            <div style="background: {bg_color}; color: white; padding: 20px; text-align: center;">
                                <h2>{icon} {message_type}</h2>
                                <p>Ticket: {self.name}</p>
                            </div>
                            <div style="padding: 20px; background-color: white;">
                                <p>Hello <strong>{recipient.name}</strong>,</p>
                                <p>This ticket is approaching its SLA deadline:</p>
                                <ul>
                                    <li><strong>Time Remaining:</strong> {hours_left:.1f} hours</li>
                                    <li><strong>Deadline:</strong> {self.sla_deadline.strftime('%B %d, %Y at %I:%M %p') if self.sla_deadline else 'Not Set'}</li>
                                    <li><strong>Priority:</strong> {dict(self._fields['priority'].selection).get(self.priority, 'Normal')}</li>
                                    <li><strong>Assigned To:</strong> {self.user_id.name or 'Unassigned'}</li>
                                </ul>
                                <p><strong>Please take immediate action to prevent SLA breach.</strong></p>
                                <p><a href="/web#id={self.id}&view_type=form&model=helpdesk.ticket" 
                                      style="background-color: #007bff; color: white; padding: 10px 20px; 
                                             text-decoration: none; border-radius: 4px;">View Ticket</a></p>
                            </div>
                        </div>
                    ''',
                    'email_to': recipient.email,
                    'auto_delete': True
                }).send()
            except Exception as e:
                # Log error but continue
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
        changes_html = '<br/>'.join([f'• {change}' for change in changes])
        self.message_post(
            body=_(
                "<div class='alert alert-info'>"
                "<h5><i class='fa fa-info-circle'></i> SLA Information Updated</h5>"
                "<p><strong>The following changes were made:</strong></p>"
                "<p>%s</p>"
                "<p><em>Relevant team members have been notified.</em></p>"
                "</div>"
            ) % changes_html,
            subtype_xmlid="mail.mt_comment",
            partner_ids=recipients.mapped('partner_id').ids
        )
        
        # Send email notifications to stakeholders
        for recipient in recipients:
            try:
                self.env['mail.mail'].create({
                    'subject': f'📋 SLA Update: {self.name}',
                    'body_html': f'''
                        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                            <div style="background: #17a2b8; color: white; padding: 15px; text-align: center;">
                                <h3>📋 SLA Information Updated</h3>
                                <p>Ticket: {self.name}</p>
                            </div>
                            <div style="padding: 20px; background-color: white;">
                                <p>Hello <strong>{recipient.name}</strong>,</p>
                                <p>Important SLA information has been updated for this ticket:</p>
                                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                                    {'<br/>'.join([f'• {change}' for change in changes])}
                                </div>
                                <p><strong>Current Status:</strong></p>
                                <ul>
                                    <li><strong>SLA Deadline:</strong> {self.sla_deadline.strftime('%B %d, %Y at %I:%M %p') if self.sla_deadline else 'Not Set'}</li>
                                    <li><strong>Priority:</strong> {dict(self._fields['priority'].selection).get(self.priority, 'Normal')}</li>
                                    <li><strong>Stage:</strong> {self.stage_id.name}</li>
                                </ul>
                                <p>Please review the changes and adjust your workflow accordingly.</p>
                                <p><a href="/web#id={self.id}&view_type=form&model=helpdesk.ticket" 
                                      style="background-color: #007bff; color: white; padding: 10px 20px; 
                                             text-decoration: none; border-radius: 4px;">View Ticket</a></p>
                            </div>
                        </div>
                    ''',
                    'email_to': recipient.email,
                    'auto_delete': True
                }).send()
            except Exception as e:
                # Log error but continue
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
        """Check for SLA breaches and send notifications"""
        now = fields.Datetime.now()
        
        # Find tickets that have breached SLA
        breached_tickets = self.search([
            ('sla_deadline', '<', now),
            ('sla_breached', '=', False),
            ('stage_id.fold', '=', False)  # Only active stages
        ])
        
        for ticket in breached_tickets:
            # Mark as breached
            ticket.write({
                'sla_breached': True,
                'sla_breach_time': now
            })
            
            # Send breach notifications
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
            # Check if breach is during working hours
            if ticket.working_time_config_id:
                working_times = self.env['helpdesk.working.time'].search([
                    ('company_id', '=', ticket.company_id.id or self.env.company.id),
                    ('active', '=', True),
                    ('day_of_week', '=', str(now.weekday()))
                ])
                
                if working_times:
                    working_time = working_times[0]
                    current_hour = now.hour + now.minute / 60.0
                    
                    # Only mark as breached if we're in working hours
                    if working_time.hour_from <= current_hour <= working_time.hour_to:
                        ticket._mark_sla_breached(now, template)
                else:
                    # No working time defined for today, check if we should breach
                    ticket._mark_sla_breached(now, template)
            else:
                # No working time configuration, use standard breach check
                ticket._mark_sla_breached(now, template)

    def _mark_sla_breached(self, breach_time, template):
        """Mark ticket as SLA breached"""
        self.sla_breach_time = breach_time
        self.sla_breached = True
        
        # Calculate how many business hours over the SLA
        if self.working_time_config_id and self.sla_deadline:
            hours_over = self._calculate_business_hours(self.sla_deadline, breach_time)
            breach_message = _(
                "<b>SLA Breach:</b> Ticket has exceeded its SLA deadline by %.2f business hours (%s)." %
                (hours_over, self.sla_deadline.strftime('%Y-%m-%d %H:%M:%S'))
            )
        else:
            breach_message = _(
                "<b>SLA Breach:</b> Ticket has exceeded its SLA deadline (%s)." %
                self.sla_deadline.strftime('%Y-%m-%d %H:%M:%S')
            )
            
        self.message_post(
            body=breach_message,
            subtype_xmlid="mail.mt_note"
        )
        
        if template:
            template.send_mail(self.id, force_send=True)

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
        if ticket.working_time_config_id and hasattr(ticket, 'sla_deadline') and ticket.ticket_type_id:
            ticket._recalculate_sla_with_working_time()
            
        return ticket
    
    def _recalculate_sla_with_working_time(self):
        """Recalculate SLA deadline considering working time configuration"""
        if not self.working_time_config_id:
            return
            
        # Get SLA policy for this ticket type
        sla_policy = self.env['helpdesk.sla'].search([
            ('ticket_type_ids', '=', self.ticket_type_id.id)
        ], limit=1)
        
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
            'view_mode': 'tree,form',
            'target': 'new',
            'domain': [('company_id', '=', self.company_id.id or self.env.company.id)],
            'context': {
                'default_company_id': self.company_id.id or self.env.company.id,
                'ticket_id': self.id,
            }
        }
    
    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        """Override message_post to detect @user mentions and create transfer lines"""
        import re
        import logging
        
        _logger = logging.getLogger(__name__)
        
        # Call parent method first
        message = super(HelpdeskTicket, self).message_post(**kwargs)
        
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
                from odoo.tools import html2plaintext
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
    
    @api.onchange('team_id')
    def _onchange_team_id_filter_types(self):
        """When team changes, filter ticket types to show only types associated with the team"""
        for rec in self:
            if rec.team_id:
                # Get ticket types configured on the team
                allowed_type_ids = rec.team_id.team_type_ids.ids or []
                
                # Clear type if it's not in the allowed types
                if rec.ticket_type_id and rec.ticket_type_id.id not in allowed_type_ids:
                    rec.ticket_type_id = False
                
                # If team has types, show them; otherwise show all types
                if allowed_type_ids:
                    return {
                        'domain': {
                            'ticket_type_id': [('id', 'in', allowed_type_ids)],
                        }
                    }
                else:
                    # Team has no types assigned, show all types
                    return {
                        'domain': {
                            'ticket_type_id': [],
                        }
                    }
            else:
                # No team selected, show all types
                return {
                    'domain': {
                        'ticket_type_id': [],
                    }
                }
    
    @api.onchange('ticket_type_id')
    def _onchange_ticket_type_filter_users(self):
        """When ticket type changes, filter assigned users to show only users assigned to that type"""
        for rec in self:
            if rec.ticket_type_id:
                # Get all users assigned to this ticket type
                allowed_user_ids = rec.ticket_type_id.user_ids.ids or []
                
                # Clear user if they're not in the allowed users
                if rec.user_id and rec.user_id.id not in allowed_user_ids:
                    rec.user_id = False
                
                # If type has users, show them; otherwise show all users
                if allowed_user_ids:
                    return {
                        'domain': {
                            'user_id': [('id', 'in', allowed_user_ids)],
                        }
                    }
                else:
                    # Type has no users assigned, show all users
                    return {
                        'domain': {
                            'user_id': [],
                        }
                    }
            else:
                # No type selected, show all users
                return {
                    'domain': {
                        'user_id': [],
                    }
                }
