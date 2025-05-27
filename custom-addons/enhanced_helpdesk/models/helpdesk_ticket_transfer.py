from odoo import models, fields, api
from datetime import datetime

class HelpdeskTicketTransfer(models.Model):
    _name = 'helpdesk.ticket.transfer'
    _description = 'Helpdesk Ticket Transfer Log'
    _order = 'transfer_date desc'
    
    
   

    ticket_id = fields.Many2one('helpdesk.ticket', required=True)
    old_team_id = fields.Many2one('helpdesk.team', string='From Team')
    new_team_id = fields.Many2one('helpdesk.team', string='To Team')
    old_user_id = fields.Many2one('res.users', string='From User')
    new_user_id = fields.Many2one('res.users', string='To User')
    reason = fields.Text(string='Reason for Transfer')
    transfer_date = fields.Datetime(string='Transfer Date', default=fields.Datetime.now)
    status = fields.Selection([
        ('inprogress', 'In Progress'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
    ], string='Status', default='inprogress', required=True)
    # Computed field
    time_to_resolve = fields.Char(string='Time Taken Before Transfer', compute='_compute_time_to_resolve')
    time_commited_to_resolve_the_ticket_by_the_team = fields.Datetime(string='Time Commited to Resolve', default=fields.Datetime.now)
    time_taken_for_the_team_to_resolve =  fields.Datetime(string='Date and Time Taken for the Team to Resolve', default=fields.Datetime.now)
    team_status_on_ticket_assigned = fields.Char(string='Team Status on Ticket Assigned', compute='_compute_team_status_on_ticket_assigned')
    
    
   
    
    
    
    @api.depends('transfer_date', 'ticket_id.create_date')
    def _compute_time_to_resolve(self):
        for rec in self:
            if rec.transfer_date and rec.ticket_id.create_date:
                delta = rec.transfer_date - rec.ticket_id.create_date
                rec.time_to_resolve = str(delta)
            else:
                rec.time_to_resolve = "N/A"
                
    @api.onchange('ticket_id')
    def _onchange_ticket_id(self):
        if self.ticket_id:
            self.old_team_id = self.ticket_id.team_id.id
            self.old_user_id = self.ticket_id.user_id.id
            
            
            
            
    
                
                
    @api.depends('status', 'time_taken_for_the_team_to_resolve', 'time_commited_to_resolve_the_ticket_by_the_team')
    def _compute_team_status_on_ticket_assigned(self):
        for rec in self:
            if rec.status == 'completed':
                if rec.time_taken_for_the_team_to_resolve > rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'Failed'
                elif rec.time_taken_for_the_team_to_resolve <= rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'Passed'
                elif rec.time_taken_for_the_team_to_resolve == rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'On Time'
            elif rec.status == 'pending':
                if rec.time_taken_for_the_team_to_resolve > rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'Failed'
                elif rec.time_taken_for_the_team_to_resolve <= rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'Passed'
                elif rec.time_taken_for_the_team_to_resolve == rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'On Time'
            elif rec.status == 'inprogress':
                if rec.time_taken_for_the_team_to_resolve > rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'Failed'
                elif rec.time_taken_for_the_team_to_resolve <= rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'Passed'
                elif rec.time_taken_for_the_team_to_resolve == rec.time_commited_to_resolve_the_ticket_by_the_team:
                    rec.team_status_on_ticket_assigned = 'On Time'
            else:
                rec.team_status_on_ticket_assigned = 'N/A'

    def transfer_as_task(self):
        for rec in self:
            if not rec.old_user_id:
                raise UserWarning("Please specify a user to assign the task to.")

            # Create the task
            task = self.env['project.task'].create({
                'name': f"Follow-up: Ticket {rec.ticket_id.name}",
                'user_ids': rec.old_user_id,
                'date_deadline': rec.time_commited_to_resolve_the_ticket_by_the_team,
                'description': f"""
                    Ticket ID: {rec.ticket_id.name}
                    Reason: {rec.reason or 'N/A'}
                    From: {rec.old_user_id.name or 'N/A'}
                    Status: {rec.status}
                    Transfer Date: {rec.transfer_date.strftime('%Y-%m-%d %H:%M:%S')}
                """,
            })
            # Compose message for the chat
            message = f"""
                <ul>
                    <li><b>Task Assigned From Ticket:</b> <a href="/web#id={rec.ticket_id.id}&model=helpdesk.ticket&view_type=form">{rec.ticket_id.name}</a></li>
                    <li><b>Assigned To:</b> {rec.old_user_id.name}</li>
                    <li><b>Date Assigned:</b> {rec.transfer_date.strftime('%Y-%m-%d %H:%M:%S')}</li>
                    <li><b>Committed Deadline To Resolve:</b> {rec.time_commited_to_resolve_the_ticket_by_the_team}</li>
                    <li><b>Task Created By:</b> {self.env.user.name}</li>
                    <li><a href="/web#id={task.id}&model=project.task&view_type=form">View Task</a></li>
                </ul>
            """

            # Send private chat message to the old_user_id (assignee)
            if rec.old_user_id and rec.old_user_id.partner_id:
                channel_info = self.env['mail.channel'].channel_get([rec.old_user_id.partner_id.id])
                channel = self.env['mail.channel'].browse(channel_info["id"])
                channel.message_post(
                    body=message,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment'
                )
            

            # Post a message to the OE-Chatter of the ticket
            rec.ticket_id.message_post(
                body="""
                    <ul>
                        <li><b>Task Assigned From Ticket:</b> # {ticket_id}</li>
                        <li><b>Assigned To:</b> {assigned_to}</li>
                        <li><b>Date Assigned:</b> {date_assigned}</li>
                        <li><b>Committed Deadline To Resolve:</b> {deadline}</li>
                        <li><b>Task Created By:</b> {created_by}</li>
                        <li><a href="/web#id={task_id}&model=project.task&view_type=form">View Task</a></li>
                    </ul>
                """.format(
                    ticket_id=rec.ticket_id.id,
                    assigned_to=rec.old_user_id.name,
                    date_assigned=rec.transfer_date.strftime('%Y-%m-%d %H:%M:%S'),
                    deadline=rec.time_commited_to_resolve_the_ticket_by_the_team,
                    created_by=self.env.user.name,
                    task_id=task.id
                ),
                subtype_xmlid="mail.mt_note"
            )