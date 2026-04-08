from odoo import models, fields, api
from . utils import format_response, post_chatter_message

TASK_STATES_SELECTION = [
    ('new', 'New'),
    ('on-going', 'On Going'),
    ('completed', 'Completed'),
    ('paused', 'Paused'),
    ('cancelled', 'Cancelled'),
]

class Project(models.Model):
    _inherit = 'project.project'

    computed_inspection_status = fields.Char(compute="_compute_vehicle_status")
    computed_inspection_remarks = fields.Char(compute="_compute_vehicle_status")
    job_card_count = fields.Integer(string='Job Card Count', compute='_get_job_cards', store=True)
    job_card_ids = fields.One2many(
        "vts.job.card",
        "project_id",
        string="Job Cards",
        compute="_get_job_cards",
        store=True,
        copy=False,
    )

    @api.depends('job_card_ids')
    def _get_job_cards(self):
        for project in self:
            project.job_card_ids = self.env['vts.job.card'].search([('project_id', '=', project.id)])
            project.job_card_count = len(project.job_card_ids)


    def open_job_cards(self):
        return {
            'name': 'Job Cards',
            'type': 'ir.actions.act_window',
            'res_model': 'vts.job.card',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
        }

    def _compute_vehicle_status(self):
        for project in self:
            # Search for the related VtsDailyCheckupList records
            checkup_lists = self.env['vts.daily.checkup.list'].search([('projects_ids', 'in', project.id)])
            status = 'No Status'
            remarks = ''
            # Iterate over the vehicle_checkup_status list to find the status for the current project
            for checkup_list in checkup_lists:
                for status_info in checkup_list.vehicle_checkup_status if checkup_list.vehicle_checkup_status else []:
                    if status_info['projects_id'] == project.id:
                        status = status_info['status']
                        remarks = status_info.get('remarks', '')
                        break
                if status != 'No Status':
                    break
            project.computed_inspection_status = status
            project.computed_inspection_remarks = remarks

    def return_all_vts_projects(self, name, limit=50):
        projects = self.search([('name', 'ilike', name)], limit=limit)
        values = []
        if projects:
            for project in projects:
                vals = {
                    'id': project.id,
                    'name': project.name,
                    'customer': project.partner_id.name,
                    'active': project.active,
                }

                values.append(vals)

        return format_response('success', 'Projects returned successfully.', values)

    def return_vts_project(self, project_id):
        project = self.search([('id', '=', project_id)], limit=1)
        values = []
        if project:

            vals = {
                'id': project.id,
                'name': project.name,
                'customer': project.partner_id.name,
                'project_manager': project.user_id.name,
                'active': project.active,
            }
            values.append(vals)

        return format_response('success', 'Project returned successfully.', values)

    def return_customer_debts(self, project_name):
        project = self.search([('name', '=', project_name)], limit=1)
        if not project:
            return format_response('error', 'Project not found.', [])

        customer = project.partner_id
        if not customer:
            return format_response('error', 'Customer not found.', [])

        debts = customer.customer_report_ids

        total_debt = sum(amount.amount_residual_signed for amount in debts)
        total_debt = round(total_debt, 2)

        return format_response('success', 'Customer debts returned successfully.', {
            'customer_id': customer.id,
            'customer_name': customer.name,
            'customer_phone': customer.phone,
            'debts': [{
                'invoice_number': debt.name,
                'date': debt.date,
                'amount_residual_signed': debt.amount_residual_signed,
            } for debt in debts],
            'total_debt': total_debt,
        })

    def customer_chatter(self, vals):
        """
        Post a message to a res.partner chatter.
        Uses the generic post_chatter_message helper.
        """
        customer_id = vals.get('customer_id')
        message_body = vals.get('message_body')

        # Use the generic helper function
        result = post_chatter_message(
            env=self.env,
            model_name='res.partner',
            record_id=customer_id,
            message_body=message_body,
            subject=f'Message regarding Project ID {vals.get("project_id")}',
        )

        return result

class Task(models.Model):
    _inherit = "project.task"

    vts_job_card = fields.Many2one('vts.job.card', string='Job Card')
    vts_employee = fields.Many2one('hr.employee', string='Technician', domain=[('is_vts_employee', '=', True)])
    vts_state = fields.Selection(TASK_STATES_SELECTION, default='new', tracking=True, string="VTS State")
    def return_employee_tasks(self, employee_id, domain=[], limit=25):
        tasks = self.search([('vts_employee', '=', employee_id)] + domain, limit=limit)
        values = []
        if tasks:
            for task in tasks:
                vals = {
                    'id': task.id,
                    'name': task.name,
                    'project': task.project_id.name,
                    'assigned_by': [manager.name for manager in task.user_ids],
                    'job_card': task.vts_job_card.name,
                    'description': task.description,
                    'state': task.vts_state,
                    'state_desc': dict(TASK_STATES_SELECTION)[task.vts_state],
                    'customer_id': task.partner_id.id,
                    'customer': task.partner_id.name,
                }
                values.append(vals)

        return format_response('success', 'Employee tasks returned successfully.', values)
    
    def return_empoyee_task_by_id(self, task_id, employee_id):
        task = self.search([('id', '=', task_id), ('vts_employee.id', '=', employee_id)], limit=1)
        if not task:
            return format_response('error', 'Task not found.', [])
        
        vals = {
            'id': task.id,
            'name': task.name,
            'project': task.project_id.name,
            'assigned_by': [manager.name for manager in task.user_ids],
            'job_card_id': task.vts_job_card.id,
            'job_card': task.vts_job_card.name,
            'description': task.description,
            'state': task.vts_state,
            'state_desc': dict(TASK_STATES_SELECTION)[task.vts_state],
            'customer_id': task.partner_id.id,
            'customer': task.partner_id.name,
            'license_plate': task.project_id.name,
        }

        return format_response('success', 'Employee task returned successfully.', vals)

    def change_vts_task_state(self, vals):
        task = self.search([('id', '=', vals['task_id'])], limit=1)
        if task:
            task.write({'vts_state': vals['state']})
            return format_response('success', 'Task state changed successfully.', [])
        return format_response('error', 'Task not found.', [])
    

    def create_job_card_from_task(self, task_id):
        task = self.search([('id', '=', task_id)], limit=1)
        if not task:
            return format_response('error', 'Task not found.', [])

        service_type = None
        if task.stage_id.name == 'Installation':
            service_type = 'installation'
        elif task.stage_id.name == 'Service routine':
            service_type = 'service-routine'

        if not task.vts_job_card:
            job_card = self.env['vts.job.card'].create({
                'task_id': task.id,
                'project_id': task.project_id.id,
                'vts_employee': task.vts_employee.id,
                'customer_id': task.partner_id.id,
                'service_type': service_type,
                'license_plate': task.project_id.name,
            })
        else:
            raise ValueError("Job card already exists for this task.")

        job_card_data = job_card.get('data', {})
        task.vts_job_card = job_card_data.get('id')

        job_card_vals = {
            'id': job_card_data.get('id'),
            'name': job_card_data.get('name'),
            'customer': job_card_data.get('customer_name'),
            'technician': job_card_data.get('technician_name'),
            'service_type': job_card_data.get('service_type'),
            'state': job_card_data.get('state'),
        }
        return format_response('success', 'Job card created successfully.', job_card_vals)
