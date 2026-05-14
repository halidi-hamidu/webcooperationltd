import re
from odoo import models, fields, api
from . utils import format_response

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    technician_id = fields.Many2one('hr.employee', string='Technician', domain=[('is_vts_employee', '=', True)])
    technician_ids = fields.Many2many(
        'hr.employee',
        'helpdesk_ticket_technician_rel',
        'ticket_id',
        'employee_id',
        string='Technicians',
        domain=[('is_vts_employee', '=', True)],
    )
    vts_job_card_ids = fields.One2many('vts.job.card', 'ticket_id', string='VTS Job Cards')
    job_card_id = fields.Many2one('vts.job.card', string='Job Cards')

    def return_employee_tickets(self, technician_id, domain=[], limit=25):
        tickets = self.sudo().search([('technician_ids', 'in', technician_id)] + domain, limit=limit, order='create_date desc')
        values = []
        if tickets:
            for ticket in tickets:
                current_technician = ticket.technician_ids.filtered(lambda t: t.id == technician_id)
                vals = {
                    'id': ticket.id,
                    'name': ticket.name,
                    'supervisor': ticket.user_id.name,
                    'technician': current_technician.name if current_technician else False,
                    'technician_id': technician_id,
                    'stage': ticket.stage_id.name,
                }
                values.append(vals)

        return format_response('success', 'Employee tasks returned successfully.', values)

    def return_ticket_details(self, ticket_id, technician_id=False):
        ticket = self.browse(ticket_id)
        if not ticket:
            return format_response('error', 'Ticket not found.', [])

        current_technician = ticket.technician_ids.filtered(lambda t: t.id == technician_id) if technician_id else False
        vals = {
            'id': ticket.id,
            'name': ticket.name,
            'description': ticket.description,
            'supervisor': ticket.user_id.name,
            'technician': current_technician.name if current_technician else False,
            'technician_id': technician_id or False,
            'stage': ticket.stage_id.name,
            'vts_job_cards': [(card.id, card.name) for card in ticket.vts_job_card_ids],
        }

        return format_response('success', 'Ticket details returned successfully.', vals)

    def create_vts_job_card(self, ticket_id, employee_id):
        ticket = self.sudo().browse(ticket_id)
        if not ticket.exists():
            return format_response('error', 'Ticket not found.', [])

        if not employee_id or employee_id not in ticket.technician_ids.ids:
            return format_response('error', 'Access denied: you are not assigned to this ticket.', [])

        if ticket.job_card_id:
            return format_response('error', 'Job Card already exists for this ticket.', [])

        project_name_match = re.search(r'-(T[0-9A-Z]+)', ticket.name)
        project_name = project_name_match.group(1) if project_name_match else False
        project = self.env['project.project'].sudo().search([('name', '=', project_name)], limit=1)

        job_card = self.env['vts.job.card'].sudo().create({
            'ticket_id': ticket.id,
            'service_type': 'service-routine',
            'vts_employee': employee_id,
            'customer_id': ticket.partner_id.id,
            'project_id': project.id if project else False,
            'license_plate': project.name if project else False,
        })

        jc_data = job_card.get('data')
        ticket.job_card_id = jc_data.get('id') if jc_data else False

        return format_response(
            'success',
            'VTS Job Card created successfully.',
            jc_data,
        )
