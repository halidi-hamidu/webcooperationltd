from odoo import models, fields,api
import json
from .utils import format_response, post_chatter_message, get_chatter_messages, get_team_partner_ids

CHECKLIST_TYPES_SELECTION = [
    ("action-taken", "Action Taken"),
    ("reported-problem", "Reported Problem"),
    ("problem-seen", "Problem Seen"),

]

OWNERSHIP_TYPES = [
    ("private", "Private"),
    ("latra", "Latra"),
]

SERVICE_TYPE_SELECTION = [
    ("installation", "New Installation"),
    ("service-routine", "Service Routine"),
    ("driver-registration", "Driver Registration"),
]

JOB_CARD_STATE = [
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("reviewed", "Reviewed"),
    ("approved", "Approved"),
    ("done", "LATRA Done"),
    ("rejected", "Rejected"),
]

INSPECTION_PROPERTIES = {
    "right_head_lights": "Right Head Lights",
    "left_fog_lights": "Left Fog Lights",
    "right_fog_lights": "Right Fog Lights",
    "radio_status": "Radio Status",
    "charging_system": "Charging System",
    "tv_status": "TV Status",
    "others": "Other Issues",
    "comments": "Additional Comments"
}

INSPECTION_PROPERTIES_VALUE = {
    "okay": "Okay",
    "not-okay": "Not Okay",
}

DAILY_CHECK_UP_LIST_SELECTION = [
    ("draft", "Draft"),
    ("submitted", "Submitted"),
]
class VtsChecklistConfig(models.Model):
    _name = "vts.checklist.config"
    _description = "VTS Checklist Config"
    _rec_name = 'name'

    key = fields.Char('Key')
    name = fields.Char('Name')
    type = fields.Selection(CHECKLIST_TYPES_SELECTION, string='Checklist Type')

class VtsJobCard(models.Model):
    _name = "vts.job.card"
    _description = "VTS Job Card"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    
    task_id = fields.Many2one('project.task', string='Task')
    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True, copy=False)
    service_type = fields.Selection(SERVICE_TYPE_SELECTION, default='installation')
    ownership_type = fields.Selection(OWNERSHIP_TYPES, string='Ownership Type', default='latra')
    # Bus Information
    name = fields.Char(
        "Job Card Number",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        # default=lambda self: self.env["ir.sequence"].next_by_code("vts.job.card"),
        compute='_compute_name',
        store=True
    )
    project_id = fields.Many2one('project.project')
    vts_employee = fields.Many2one("hr.employee", string="Technician", domain=[('is_vts_employee', '=', True)])
    customer_id = fields.Many2one("res.partner", string="Customer")
    customer_mobile = fields.Char(related="customer_id.phone", string="Customer Mobile")
    customer_address = fields.Char(related="customer_id.contact_address")
    customer_phone = fields.Char(string="Customer Phone")
    business_name = fields.Char(string="Business Name")
    customer_signature = fields.Binary()
    name_of_signatory = fields.Char("Name of Signatory")
    driver_name = fields.Char("Driver Name")
    driver_mobile = fields.Char("Driver Mobile No")
    driver_license = fields.Char("Driver License")
    license_plate = fields.Char("Vehicle No", tracking=True)
    vehicle_model = fields.Many2one('fleet.vehicle.model', string='Vehicle Model')
    vehicle_make = fields.Char(related='vehicle_model.brand_id.name', string='Vehicle Make')

    state = fields.Selection(JOB_CARD_STATE, default="draft", tracking=True)
    # Installation
    serial_number = fields.Many2one(
        "stock.lot", string="Lot/Serial Number", tracking=True
    )
    imei = fields.Char("IMEI", tracking=True)
    sim_card = fields.Char("SIM Card", tracking=True)
    tag_id = fields.Char("Tag", tracking=True)

    
    service_date = fields.Date('Date of Service') 

    # Vehicle Inspection
    vehicle_inspection = fields.Json()
    inspection_html_table = fields.Html("Inspection Checklist", compute='_compute_inspection_html_table')

    # Service
    reported_problems = fields.Json()
    reported_problems_display = fields.Html(
        "Reported Problem", compute="_compute_reported_problems"
    )
    reported_problems_text = fields.Text("Reported Problem", compute="_compute_reported_problems_text", store=False)

    problems_seen = fields.Json()
    problems_seen_display = fields.Html("Problems Seen", compute="_compute_problems_seen")

    actions_taken = fields.Json()
    actions_taken_display = fields.Html('Action Taken', compute="_compute_actions_taken")

    # Customer Notes
    # customer_signature = fields.Many2one
    signed_date = fields.Date()
    attachments = fields.Many2many('ir.attachment', string="Attachments")

    # Customer Feedback
    customer_satisfaction_rating = fields.Selection(
        selection=[
            ('0', 'Hakuna'),
            ('1', '⭐'),
            ('2', '⭐⭐'),
            ('3', '⭐⭐⭐'),
            ('4', '⭐⭐⭐⭐'),
            ('5', '⭐⭐⭐⭐⭐'),
        ],
        string="Umeridhishwa kwa kiwango gani na huduma uliyopokea?",
        default='0',
        help="Customer satisfaction rating from 1 to 5 stars"
    )
    customer_liked_most = fields.Text(
        string="Ni jambo gani ulilolipenda zaidi kuhusu huduma yetu?"
    )
    customer_improvement_suggestions = fields.Text(
        string="Ni maeneo gani unadhani tunaweza kuboresha ili kukuhudumia vizuri zaidi?"
    )

    referee_id = fields.Many2one('hr.employee', string='Referee', domain=[('is_vts_employee', '=', True)])
    location = fields.Char('Location')
    general_remarks = fields.Text('General Remarks')

    def _handle_attachments(self, attachment_vals, rec_id):
        """Handle the creation of attachments."""
        for attachment in attachment_vals:
            attachment.update({
                'res_model': 'vts.job.card',
                'res_id': rec_id.id,
            })
            self.env['ir.attachment'].create(attachment)

            
    @api.depends('vts_employee')
    def _compute_name(self):
        for record in self:
            record.name = f'{record.vts_employee.barcode}{self.env["ir.sequence"].next_by_code("vts.job.card")}'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            try:
                # Ensure the name is set
                if 'name' not in vals or not vals['name']:
                    employee = self.env['hr.employee'].browse(vals.get('vts_employee'))
                    if employee:
                        vals['name'] = f'{employee.barcode}-{self.env["ir.sequence"].next_by_code("vts.job.card")}'
                    else:
                        vals['name'] = self.env["ir.sequence"].next_by_code("vts.job.card")

                # Auto-populate customer_id for service routine from project
                if vals.get('service_type') == 'service-routine' and not vals.get('customer_id'):
                    license_plate = vals.get('license_plate')
                    if license_plate:
                        # Search for project with name matching the license plate
                        project = self.env['project.project'].search([('name', '=', license_plate)], limit=1)
                        if project and project.partner_id:
                            vals['customer_id'] = project.partner_id.id
                            vals['project_id'] = project.id

                # Extract and handle attachments
                attachment_vals = vals.pop('attachments', [])
                res = super(VtsJobCard, self).create(vals)

                if res:
                    self._handle_attachments(attachment_vals, res)
                    res.service_date = fields.Datetime.now()
                    res.state = "draft"

                jobcard_vars = {
                    'id': res.id,
                    'name': res.name,
                    'customer_name': res.customer_id.name if res.customer_id else '',
                    'technician': res.vts_employee.name if res.vts_employee else '',
                    'service_type': res.service_type,
                    'state': res.state,
                }


                return format_response('success', 'Job card created successfully.', jobcard_vars)
            except Exception as e:
                return format_response('error', str(e), None)
    
    def write(self, vals):
        attachment_vals = vals.pop('attachments', [])
        res = super(VtsJobCard, self).write(vals)
        if res:
            for record in self:
                self._handle_attachments(attachment_vals, record)
        return format_response('success', 'Job card updated successfully.', res)

    def _action_submit(self):
        for record in self:
            record.state = 'submitted'

            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            job_card_url = f"{base_url}/web#id={record.id}&model=vts.job.card&view_type=form"

            # --- Job card submitted notification ---
            partner_ids = get_team_partner_ids(self.env, 'job_card_submitted')
            if partner_ids:
                message = f"""
                    <p>Job Card <a href="{job_card_url}">{record.name}</a> has been submitted.</p>
                    <p><strong>Technician:</strong> {record.vts_employee.name if record.vts_employee else 'N/A'}</p>
                    <p><strong>Customer:</strong> {record.customer_id.name if record.customer_id else 'N/A'}</p>
                    <p><strong>Vehicle:</strong> {record.license_plate if record.license_plate else 'N/A'}</p>
                    <p><strong>Service Type:</strong> {dict(SERVICE_TYPE_SELECTION).get(record.service_type, 'N/A')}</p>
                """
                record.message_post(
                    body=message,
                    subject=f'Job Card {record.name} Submitted',
                    partner_ids=partner_ids,
                    message_type='notification',
                    subtype_xmlid='mail.mt_comment',
                    body_is_html=True,
                )

            # --- Customer feedback notification (only when feedback was provided) ---
            has_feedback = (
                record.customer_satisfaction_rating and record.customer_satisfaction_rating != '0'
            ) or record.customer_liked_most or record.customer_improvement_suggestions

            if has_feedback:
                feedback_partner_ids = get_team_partner_ids(self.env, 'feedback_submitted')
                if feedback_partner_ids:
                    rating_label = dict(record._fields['customer_satisfaction_rating'].selection).get(
                        record.customer_satisfaction_rating, 'N/A'
                    )
                    feedback_message = f"""
                        <p>Customer feedback was submitted with Job Card <a href="{job_card_url}">{record.name}</a>.</p>
                        <p><strong>Customer:</strong> {record.customer_id.name if record.customer_id else 'N/A'}</p>
                        <p><strong>Rating:</strong> {rating_label}</p>
                        <p><strong>Liked most:</strong> {record.customer_liked_most or 'N/A'}</p>
                        <p><strong>Improvement suggestions:</strong> {record.customer_improvement_suggestions or 'N/A'}</p>
                    """
                    record.message_post(
                        body=feedback_message,
                        subject=f'Customer Feedback on Job Card {record.name}',
                        partner_ids=feedback_partner_ids,
                        message_type='notification',
                        subtype_xmlid='mail.mt_comment',
                        body_is_html=True,
                    )

        return format_response('success', 'Job card submitted successfully.', self.id)
    
    def action_create_project_from_job_card(self):
        for record in self:
            existing_project = self.env['project.project'].search([('name', '=', record.license_plate)], limit=1)
            # Fetch stages
            service_task_stage = self.env['vts.task.stages'].search([('key', '=', 'service-routine')], limit=1)
            new_installation_task_stage = self.env['vts.task.stages'].search([('key', '=', 'installation')], limit=1)
            if existing_project:
                record.project_id = existing_project.id
            else:
                project = self.env['project.project'].sudo().create({
                    'name': record.license_plate,
                    'partner_id': record.customer_id.id,
                    'active': True,
                })
                record.project_id = project.id

            if record.service_type == 'installation':

                # Create task
                task = self.env['project.task'].sudo().create({
                    'name': 'New Installation',
                    'project_id': record.project_id.id,  # Use the project linked to the job card
                    'stage_id': new_installation_task_stage.stage.id,
                    'vts_employee': record.vts_employee.id,
                    'vts_job_card': record.id,
                })

                record.task_id = task.id

            elif record.service_type == 'service-routine':
                # Create task
                task = self.env['project.task'].sudo().create({
                    'name': 'Service Routine',
                    'project_id': record.project_id.id,  # Use the project linked to the job card
                    'stage_id': service_task_stage.stage.id,
                    'vts_employee': record.vts_employee.id,
                    'vts_job_card': record.id,
                })

                record.task_id = task.id

        return True

    def action_get_report(self):
        return self.env.ref('ictpack_vts.action_report_job_card').report_action(self)
    
    def _compute_inspection_html_table(self):
        for record in self:            
            # Start building the HTML table
            table_html = """
            <table class="table table-striped table-bordered">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
            """
            
            # Loop through the list and create table rows
            if self.vehicle_inspection:

                for item in self.vehicle_inspection:
                    name = item['name']
                    status = item['status']
                    table_html += f"<tr><td>{INSPECTION_PROPERTIES.get(name, name)}</td><td>{INSPECTION_PROPERTIES_VALUE.get(status, status)}</td></tr>"
            else:
                table_html = "<p>No vehicle inspections available.</p>"

            # Close the table
            table_html += """
                </tbody>
            </table>
            """
            
            # Assign the HTML to the computed field
            record.inspection_html_table = table_html

    def _compute_reported_problems_text(self):
        for rec in self:
            if rec.reported_problems:
                checklist_items = self.env['vts.checklist.config'].search([('id', 'in', rec.reported_problems)])
                rec.reported_problems_text = ', '.join(checklist_items.mapped('name'))
            else:
                rec.reported_problems_text = ''

    def _compute_reported_problems(self):
        for rec in self:
            rec.reported_problems_display = self._generate_html_table_for(rec.reported_problems)
    
    def _compute_problems_seen(self):
        for rec in self:
            rec.problems_seen_display =  self._generate_html_table_for(rec.problems_seen)

    
    def _compute_actions_taken(self):
        for rec in self:
            rec.actions_taken_display =  self._generate_html_table_for(rec.actions_taken)
    

    def _generate_html_table_for(self, field_data):
        if not field_data:
            return ""
        # Start building the HTML table
        table_html = """
        <table class="table table-striped table-bordered">
            <thead>
                <tr>
                    <th>Name</th>
                </tr>
            </thead>
            <tbody>
        """
        
        # Loop through the list and create table rows
        checklist_items = self.env['vts.checklist.config'].search([('id', 'in', field_data)])  
        for item in checklist_items:  
            table_html += f"<tr><td>{item.name}</td></tr>"
        
        # Close the table
        table_html += """
            </tbody>
        </table>
        """
        
        # Assign the HTML to the computed field
        return table_html

    def return_employee_job_cards(self, employee_id, domain=None, limit=25, offset=0):
        extra_domain = list(domain if domain else [])
        has_state_filter = any(
            isinstance(leaf, (list, tuple)) and len(leaf) >= 1 and leaf[0] == 'state'
            for leaf in extra_domain
        )
        base_domain = [('vts_employee', '=', employee_id)]
        if not has_state_filter:
            base_domain.append(('state', '!=', 'done'))
        search_domain = base_domain + extra_domain
        
        # Get total count
        total_count = self.search_count(search_domain)
        
        # Get paginated records
        job_card = self.search(search_domain, limit=limit, offset=offset, order='id desc')

        values = []
        for record in job_card:
            attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'vts.job.card'),
                ('res_id', '=', record.id)
            ])

            attachment_data = [{
                'name': attachment.name,
                'url': '/web/content/%s/%s' % (attachment.id, attachment.name),
                'mimetype': attachment.mimetype,
            } for attachment in attachments]

            values.append({
                'id': record.id,
                'name': record.name,
                'task_id': record.task_id.id,
                'task_name': record.task_id.name,
                'customer_id': record.customer_id.name if record.customer_id else '',
                'vehicle_model': record.vehicle_model.id,
                'vehicle_no': record.license_plate,
                'state': record.state,
                'state_desc': dict(JOB_CARD_STATE)[record.state],
                'service_type': record.service_type,
                # 'service_type_desc': dict(SERVICE_TYPE_SELECTION)[record.service_type],
                'service_date': record.service_date,
                'attachments': attachment_data,
                'vehicle_inspection': record.vehicle_inspection,
                'imei': record.imei,
                'serial_number': record.serial_number.name,
                'sim_card': record.sim_card,
                'tag_id': record.tag_id,
                'reported_problems': record.reported_problems,
                'problems_seen': record.problems_seen,
                'actions_taken': record.actions_taken,
                'customer_signature': record.customer_signature,
                'driver_name': record.driver_name,
                'driver_mobile': record.driver_mobile,
                'driver_license': record.driver_license,

            })

        return format_response('success', 'Employee jobcard returned successfully.', {
            'records': values,
            'total_count': total_count,
            'limit': limit,
            'offset': offset
        })

    def vts_employee_dashboard(self, employee_id):
        employee_stock_location = self.env['hr.employee'].search([('id', '=', employee_id)], limit=1).employee_stock_location
        total_installations_domain = [('vts_employee', '=', employee_id), ('stage_id.name', '=', 'Installation')]
        total_employee_tasks = None
        
        # start_of_day = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # end_of_day = fields.Datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)

        new_instalation_domain = [('vts_employee', '=', employee_id), ('service_type', '=', 'installation')]
        service_routine_domain = [('vts_employee', '=', employee_id), ('service_type', '=', 'service-routine')]

        new_tasks_domain = [('vts_employee', '=', employee_id), ('vts_state', '=', 'new')]
        pending_tasks_domain = [('vts_employee', '=', employee_id), ('vts_state', '=', 'paused')]
        completed_tasks_domain = [('vts_employee', '=', employee_id), ('vts_state', '=', 'completed')]
        vehicle_checklist_draft_domain = [('employee_id', '=', employee_id), ('state', '=', 'draft')]
        vehicle_checklist_submitted_domain = [('employee_id', '=', employee_id), ('state', '=', 'submited')]
        ticket_domain = [('technician_ids', 'in', employee_id)]

        device_in_stock_count = self.env['stock.lot'].return_employee_vtds_instock(employee_id, [], True)
        new_tasks = self.env['project.task'].search_count(new_tasks_domain)
        peending_tasks = self.env['project.task'].search_count(pending_tasks_domain)
        completed_tasks = self.env['project.task'].search_count(completed_tasks_domain)
        total_installation = self.env['vts.job.card'].search_count(new_instalation_domain)
        total_service_routine = self.env['vts.job.card'].search_count(service_routine_domain)
        vehicle_checklist_draft_count = self.env['vts.daily.checkup.list'].search_count(vehicle_checklist_draft_domain)
        vehicle_checklist_submitted_count = self.env['vts.daily.checkup.list'].search_count(vehicle_checklist_submitted_domain)
        ticket_count = self.env['helpdesk.ticket'].sudo().search_count(ticket_domain)

        vals = {
            "device_in_stock": device_in_stock_count['data'],
            "tasks": {
                "new": new_tasks,
                "pending": peending_tasks,
                "completed": completed_tasks,
            },
            "vehicle_checklist_count": {
                "draft": vehicle_checklist_draft_count,
                "submitted": vehicle_checklist_submitted_count,
            },
            "total_installation": total_installation,
            "total_service_routine": total_service_routine,
            "ticket_count": ticket_count,
        }

        return format_response('success', 'Employee dashboard data returned successfully.', vals)

    def return_vehicle_models(self):
        fleets = self.env['fleet.vehicle.model'].search([])
        fleet_data = []
        for fleet in fleets:
            fleet_data.append({
                'id': fleet.id,
                'name': fleet.name,
                'brand': fleet.brand_id.name,
                'year': fleet.model_year,
            })
        return format_response('success', 'Vehicle models returned successfully.', fleet_data)
    
    def _get_jobcard_chatter(self, jobcard_id):
        return get_chatter_messages(self.env, 'vts.job.card', jobcard_id)
    
    def return_jobcard_by_id(self, job_card_id):
        job_card = self.search([('id', '=', job_card_id)])
        if not job_card:
            return format_response('error', 'Job card not found.', None)

        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'vts.job.card'),
            ('res_id', '=', job_card.id)
        ])

        attachment_data = [{
            'name': attachment.name,
            'url': '/web/content/%s/%s' % (attachment.id, attachment.name),
            'mimetype': attachment.mimetype,
        } for attachment in attachments]

        message_data = self._get_jobcard_chatter(job_card.id)
 
        values = {
            'id': job_card.id,
            'name': job_card.name,
            'task_id': job_card.task_id.id,
            'ticket_name': job_card.ticket_id.name if job_card.ticket_id else '',
            'task_name': job_card.task_id.name,
            'customer_id': job_card.customer_id.name,
            'customer_phone': job_card.customer_phone,
            'business_name': job_card.business_name,
            'driver_name': job_card.driver_name,
            'driver_mobile': job_card.driver_mobile,
            'driver_license': job_card.driver_license,
            'name_of_signatory': job_card.name_of_signatory,
            'vehicle_model': job_card.vehicle_model.name,
            'vehicle_no': job_card.license_plate,
            'state': job_card.state,
            'state_desc': dict(JOB_CARD_STATE)[job_card.state],
            'service_type': job_card.service_type,
            'service_type_desc': dict(SERVICE_TYPE_SELECTION)[job_card.service_type],
            'service_date': job_card.service_date,
            'attachments': attachment_data,
            'messages': message_data,
            'vehicle_inspection': job_card.vehicle_inspection,
            'imei': job_card.imei,
            'serial_number': job_card.serial_number.name,
            'sim_card': job_card.sim_card,
            'tag_id': job_card.tag_id,
            'reported_problems': job_card.reported_problems,
            'problems_seen': job_card.problems_seen,
            'actions_taken': job_card.actions_taken,
            'customer_signature': job_card.customer_signature,
            'general_remarks': job_card.general_remarks,
            'location': job_card.location,
            'customer_satisfaction_rating': job_card.customer_satisfaction_rating,
            'customer_liked_most': job_card.customer_liked_most,
            'customer_improvement_suggestions': job_card.customer_improvement_suggestions,
        }

        return format_response('success', 'Job card returned successfully.', values)
    
    def jobcard_chatter(self, vals):
        job_card = vals.get('job_card_id')
        message_body = vals.get('message_body')

        # Use the generic helper function
        result = post_chatter_message(
            env=self.env,
            model_name='vts.job.card',
            record_id=job_card,
            message_body=message_body,
            subject=f'New Message on Job Card {job_card}',
        )
        
        return result
    
    def action_reviewed(self):
        for record in self:
            record.state = 'reviewed'
        return True
    
    def action_approved(self):
        for record in self:
            record.state = 'approved'
        return True
    
    def action_done(self):
        for record in self:
            record.state = 'done'
    
    def action_rejected(self):
        for record in self:
            record.state = 'rejected'
        return True
    
    def action_create_sale_order(self):
        """Create a sale order from the job card if it's approved and no sale order exists."""
        self.ensure_one()
        
        # Check if job card is approved
        if self.state != 'approved':
            return format_response('error', 'Job card must be in approved state to create a sale order.', None)
        
        # Check if sale order already exists
        if self.sale_order_id:
            return format_response('error', 'Sale order already exists for this job card.', {
                'sale_order_id': self.sale_order_id.id,
                'sale_order_name': self.sale_order_id.name
            })
        
        # Check if customer exists
        if not self.customer_id:
            return format_response('error', 'Customer is required to create a sale order.', None)
        
        try:
            # Create sale order
            sale_order_vals = {
                'partner_id': self.customer_id.id,
                'date_order': fields.Datetime.now(),
                'origin': self.name,
                'note': f'Created from Job Card: {self.name}\n'
                        f'Service Type: {dict(SERVICE_TYPE_SELECTION).get(self.service_type, "")}\n'
                        f'Vehicle No: {self.license_plate or ""}\n'
                        f'IMEI: {self.imei or ""}\n'
                        f'Serial Number: {self.serial_number.name if self.serial_number else ""}',
            }
            
            # Add project if exists
            if self.project_id:
                sale_order_vals['project_id'] = self.project_id.id
            
            sale_order = self.env['sale.order'].create(sale_order_vals)
            
            # Link sale order to job card
            self.sale_order_id = sale_order.id
            
            # Post message to job card
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            sale_order_url = f"{base_url}/web#id={sale_order.id}&model=sale.order&view_type=form"
            message = f'<p>Sale Order <a href="{sale_order_url}">{sale_order.name}</a> has been created from this job card.</p>'
            self.message_post(
                body=message,
                subject=f'Sale Order {sale_order.name} Created',
                message_type='notification',
                subtype_xmlid='mail.mt_comment',
                body_is_html=True,
            )
            
            return format_response('success', 'Sale order created successfully.', {
                'sale_order_id': sale_order.id,
                'sale_order_name': sale_order.name,
                'job_card_id': self.id
            })
            
        except Exception as e:
            return format_response('error', f'Failed to create sale order: {str(e)}', None)
    
    def action_create_ticket_wizard(self):
        """Open wizard to create ticket from job card."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Ticket',
            'res_model': 'create.ticket.from.jobcard.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_job_card_id': self.id,
                'default_technician_id': self.vts_employee.id if self.vts_employee else False,
                'default_partner_id': self.customer_id.id if self.customer_id else False,
            },
        }
    
    def search_customers(self, search_term):
        customers = self.env['res.partner'].search([
            ('name', 'ilike', search_term),
            ('customer_rank', '>', 0)
        ], limit=10)

        customer_data = []
        for customer in customers:
            customer_data.append({
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
            })

        return format_response('success', 'Customers returned successfully.', customer_data)
    
class VtsProblems(models.Model):
    _name = "vts.reported.problems"
    _description = "VTD Problems"

    key = fields.Char()
    value = fields.Char(string='Name')


class VtsProblemSeen(models.Model):
    _name = "vts.problem.seen"
    _description = "VTD Problem Seen"

    key = fields.Char()
    value = fields.Char(string='Name')

class VtsTaskStages(models.Model):
    _name = "vts.task.stages"
    _description = "VTD Task Stages"

    key = fields.Char()
    name = fields.Char(string='Name')
    stage = fields.Many2one('project.task.type', string='Stage')


class VtsDailyCheckupList(models.Model):
    _name = "vts.daily.checkup.list"
    _description = "VTD Daily Checkup List"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc"

    name = fields.Char(string='Name', default=lambda self: self.env['ir.sequence'].next_by_code('vts.daily.checkup.list'))
    created_date_time = fields.Datetime('Created Date Time')
    projects_ids = fields.Many2many('project.project', string='Project', required=False)
    location_name = fields.Char(string='Location', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    state = fields.Selection(DAILY_CHECK_UP_LIST_SELECTION, string='State', default='draft')
    vehicle_checkup_status = fields.Json()


    def create(self, vals):
        try:
            vals['created_date_time'] = fields.Datetime.now()
            res = super(VtsDailyCheckupList, self).create(vals)
        except Exception as e:
            return format_response('error', str(e), None)

        return format_response('success', 'Daily checkup list created successfully.', res.id)
    
    def action_submit(self):
        for record in self:
            record.state = 'submited'
        return True
    
    def return_checklist(self, employee_id):
        checklists = self.search([('employee_id', '=', employee_id)])
        values = []

        for checklist in checklists:
            # Build a mapping from project_id to status
            status_map = {
                entry.get('projects_id'): entry.get('status')
                for entry in (checklist.vehicle_checkup_status or [])
                if entry.get('projects_id') is not None
            }

            projects = []
            for project in checklist.projects_ids:
                partner = project.partner_id
                if not partner:
                    total_debt = 0.0
                else:
                    # If partner is a recordset, take the first one
                    single_partner = partner[0]
                    debts = single_partner.customer_report_ids
                    total_debt = round(
                        sum(amount.amount_residual_signed for amount in debts), 2
                    ) if debts else 0.0

                projects.append({
                    'project_id': project.id,
                    'project_name': project.name or '',
                    'project_status': status_map.get(project.id, '') or '',
                    'total_debt': total_debt,
                })

            values.append({
                'id': checklist.id or '',
                'name': checklist.name or '',
                'state': (checklist.state or '').upper(),
                'date': checklist.created_date_time or '',
                'location_name': checklist.location_name or '',
                'projects': projects,
            })

        return format_response('success', 'Checklist returned successfully.', values)
