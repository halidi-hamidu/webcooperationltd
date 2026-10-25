# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class CreateTicketFromJobCardWizard(models.TransientModel):
    _name = 'create.ticket.from.jobcard.wizard'
    _description = 'Create Ticket from Job Card Wizard'

    job_card_id = fields.Many2one('vts.job.card', string='Job Card', readonly=True)
    team_id = fields.Many2one('helpdesk.team', string='Team', required=True)
    user_id = fields.Many2one('res.users', string='Assigned To', required=True)
    technician_id = fields.Many2one('hr.employee', string='Technician', 
                                    domain=[('is_vts_employee', '=', True)], 
                                    readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer')
    name = fields.Char(string='Ticket Name', required=True)
    description = fields.Html(string='Description')
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Medium'),
        ('2', 'High'),
        ('3', 'Urgent')
    ], string='Priority', default='1')

    @api.model
    def default_get(self, fields_list):
        """Override to set default values from job card."""
        res = super(CreateTicketFromJobCardWizard, self).default_get(fields_list)
        
        job_card_id = self.env.context.get('active_id')
        if job_card_id:
            job_card = self.env['vts.job.card'].browse(job_card_id)
            
            res['job_card_id'] = job_card.id
            res['technician_id'] = job_card.vts_employee.id if job_card.vts_employee else False
            res['partner_id'] = job_card.customer_id.id if job_card.customer_id else False
            
            # Generate default ticket name
            service_type_label = dict(job_card._fields['service_type'].selection).get(job_card.service_type, '')
            default_name = f"{service_type_label} - {job_card.license_plate or 'Job Card'}"
            res['name'] = default_name
            
        return res

    def action_create_ticket(self):
        """Create the ticket and link it to the job card."""
        self.ensure_one()
        
        if not self.team_id:
            raise UserError('Please select a team.')
        
        if not self.user_id:
            raise UserError('Please assign the ticket to a user.')
        
        # Create the ticket
        ticket_vals = {
            'name': self.name,
            'team_id': self.team_id.id,
            'user_id': self.user_id.id,
            'technician_id': self.technician_id.id if self.technician_id else False,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'description': self.description,
            'priority': self.priority,
            'job_card_id': self.job_card_id.id,
        }
        
        ticket = self.env['helpdesk.ticket'].create(ticket_vals)
        
        # Link the ticket to the job card
        self.job_card_id.write({'ticket_id': ticket.id})
        
        # Return action to open the created ticket
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ticket',
            'res_model': 'helpdesk.ticket',
            'res_id': ticket.id,
            'view_mode': 'form',
            'target': 'current',
        }
