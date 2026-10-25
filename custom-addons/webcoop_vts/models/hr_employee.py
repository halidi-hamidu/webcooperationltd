from datetime import timedelta
import uuid
import re
import base64
import logging
from passlib.context import CryptContext
from odoo import fields, models, api
from odoo.exceptions import UserError
from . utils import format_response

_logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VTS_EMPLOYEE_ROLES_SELECTION = [
    ('technical-team-lead', 'Technical Team Lead'),
    ('senior-technician', 'Senior Technician'),
    ('technician', 'Technician')

]

class ResPartner(models.Model):
    _inherit = 'hr.employee'

    vts_username = fields.Char(related='work_email', string='Username')
    vts_password = fields.Char('Password')
    is_vts_employee = fields.Boolean('Is VTS Employee')
    vts_employee_role = fields.Selection(VTS_EMPLOYEE_ROLES_SELECTION, default=lambda self: 'technician' if self.is_vts_employee else False)
    employee_stock_location = fields.Many2one('stock.location')
    reset_token = fields.Char('Reset Token')
    reset_token_expiry = fields.Datetime('Reset Token Expiry')
    reset_password_link = fields.Char(string='Signup URL')

    # @api.model
    # def create(self, vals):
    #     if 'vts_password' in vals:
    #         vals['vts_password'] = pwd_context.hash(vals['vts_password'])
    #     return super(ResPartner, self).create(vals)

    # def write(self, vals):
    #     if 'vts_password' in vals:
    #         vals['vts_password'] = pwd_context.hash(vals['vts_password'])
    #     return super(ResPartner, self).write(vals)
    
    def login(self, vals):
        """
        Logs in an employee with the given username and password.
        Args:
            vals (dict): A dictionary containing the username and password.
        Returns:
            dict: A dictionary containing the employee's information if the login is successful.
        Raises:
            UserError: If the username or password is invalid.
        """
        username = vals['username']
        password = vals['password']
        employee = self.search([('vts_username', '=', username), ('vts_password', '=', password), ('is_vts_employee', '=', True), ('active', '=', True)], limit=1)
        if not employee:
            raise UserError('Invalid username or password.')
        # if not employee.vts_password :
        #     raise UserError('Invalid username or password.')
        
        return {
            'id': employee.id,
            'name': employee.name,
            'username': employee.vts_username,
            'work_phone': employee.work_phone,
            'work_location': employee.work_location_id.name,
            'work_location_id': employee.work_location_id.id,
            'badge_id': employee.barcode,
            'job_position': employee.job_id.name
        }

    def return_vts_employees(self):
        """
        Returns a list of dictionaries containing information about VTS employees.

        This method searches for employees who are marked as VTS employees and are active.
        It then constructs a list of dictionaries with the following information for each employee:
        - id: The employee's ID.
        - name: The employee's name.
        - username: The employee's VTS username.
        - work_location: The name of the employee's work location.

        Returns:
            list: A list of dictionaries, each containing information about a VTS employee.
        """
        employees = self.search([('is_vts_employee', '=', True), ('active', '=', True)])

        values = []
        for rec in employees:
            vals = {
                "id": rec.id,
                "name": rec.name,
                "username": rec.vts_username,
                "work_location": rec.work_location_id.name
            }
            values.append(vals)
        return values
    
    def generate_reset_token(self):
        """
        Generates a reset token for each employee and sets an expiry time of 1 hour.

        This method iterates over each employee record, generates a unique reset token using UUID,
        and sets the token expiry time to 1 hour from the current time. The generated token and
        expiry time are then written to the employee record.

        Returns:
            str: The generated reset token.
        """
        for employee in self:
            token = str(uuid.uuid4())
            expiry = fields.Datetime.now() + timedelta(hours=1)  # Token expires in 1 hour
            employee.write({
                'reset_token': token,
                'reset_token_expiry': expiry,

            })
            return token

    def send_reset_password_sms(self, phone):
        """
        Sends a password reset SMS to the employee's phone number.

        Args:
            phone (dict): A dictionary containing the employee's phone number.

        Raises:
            UserError: If the phone number is not provided, if the user does not have an VTS username set,
                or if the provided phone number does not match the user's work or mobile phone.

        Returns:
            dict: A dictionary if the message was successfully sent to the recipient, otherwise a dictionary that contains an errorCode.
        """
        employee_phone = phone['phone']
        if not employee_phone:
            raise UserError("Phone number is required.")

        employee = self.search(['|', ('work_phone', '=', employee_phone), ('mobile_phone', '=', employee_phone)])
        if not employee:
            raise UserError('The user does not have an VTS username set.')

        if employee_phone not in [employee.work_phone, employee.mobile_phone]:
            raise UserError("The provided phone number does not match the user's work or mobile phone.")

        token = employee.generate_reset_token()
        reset_link = f"{self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/reset_password?token={token}"
        employee.write({
            'reset_password_link': reset_link
        })

        recipient = employee_phone
        company = self.env.company.name

        message = f"""
            Hello {employee.name},
            It seems you've requested a password reset. Click the link below to reset your password:
            {reset_link}
            If you didn't request this, please ignore this message.
            Thank you,
            {company}
            """

        send_message = self.env['sms.notification'].send_with_infobip(recipient, message)
        _logger.info("Password reset message sent for user <%s> to <%s>", employee.name, employee.work_email)
        return send_message

    def verify_reset_token(self, token):
        """
        Verifies the reset token for an employee.

        Args:
            token (str): The reset token to verify.

        Raises:
            UserError: If the reset token is invalid or has expired.

        Returns:
            recordset: The employee record with the valid reset token.
        """
        employee = self.search([('reset_token', '=', token), ('reset_token_expiry', '>', fields.Datetime.now())], limit=1)
        if not employee:
            raise UserError('The reset token is invalid or has expired.')
        return employee

    def reset_password(self, values):
        """
        Resets the password for an employee using the provided reset token and new password.

        Args:
            values (dict): A dictionary containing the reset token and new password.

        Raises:
            UserError: If the reset token is invalid or has expired.
        """
        employee = self.verify_reset_token(values['token'])
        new_password = values['new_password'][:72]  # Truncate to 72 bytes
        hashed_password = pwd_context.hash(new_password)
        employee.write({
            'vts_password': hashed_password,
            'reset_token': False,
            'reset_token_expiry': False,
        })

class HrWorkLocation(models.Model):
    _inherit = 'hr.work.location'

    is_vts_location = fields.Boolean('VTS Location')


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    work_location_coordinates = fields.Char('Work Location Coordinates')
    employee_photo = fields.Binary('Employee Photo')

    def check_in_employee(self, values):
        """
        Checks in an employee by creating an attendance record.

        Args:
            values (dict): A dictionary containing the employee ID, work location coordinates, and employee photo.

        Raises:
            UserError: If the employee has already checked in for today.

        Returns:
            dict: A formatted response indicating the success or failure of the check-in operation.
        """
        employee = self.env['hr.employee'].browse(values['employee_id'])
        today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Check if employee already has an open attendance
        attendance = self.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', today_start),
            ('check_out', '=', False)
        ], limit=1)
        
        if attendance:
            raise UserError('You have already checked in for today.')

        # Create attendance record
        attendance = self.create({
            'employee_id': employee.id,
            'check_in': fields.Datetime.now(),
            'work_location_coordinates': values.get('work_location_coordinates'),
            'employee_photo': values.get('employee_photo'),
        })
        
        if attendance:
            return format_response('success', 'Check in successful.', attendance.id)
        else:
            return format_response('error', 'Check in failed.', None)
    
    def check_out_employee(self, values):
        """
        Checks out an employee by updating the attendance record.

        Args:
            values (dict): A dictionary containing the employee ID and optionally employee photo.

        Raises:
            UserError: If the employee has not checked in for today.

        Returns:
            dict: A formatted response indicating the success or failure of the check-out operation.
        """
        employee = self.env['hr.employee'].browse(values['employee_id'])
        today_start = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Find open attendance for today
        attendance = self.search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', today_start),
            ('check_out', '=', False)
        ], limit=1)
        
        if not attendance:
            raise UserError('You have not checked in for today.')

        # Update attendance with check-out time
        attendance.write({
            'check_out': fields.Datetime.now(),
            'employee_photo': values.get('employee_photo'),
        })
        
        if attendance:
            return format_response('success', 'Check out successful.', attendance.id)
        else:
            return format_response('error', 'Check out failed.', None)

    def action_open_map(self):
        """Opens Google Maps with the work location coordinates."""
        self.ensure_one()
        
        if not self.work_location_coordinates:
            raise UserError('No coordinates available for this attendance record.')
        
        # Extract latitude and longitude
        match = re.search(r'lat:\s*(-?\d+\.\d+),\s*lng:\s*(-?\d+\.\d+)', self.work_location_coordinates)
        if match:
            latitude = match.group(1)
            longitude = match.group(2)
            return {
                'type': 'ir.actions.act_url',
                'url': f'https://www.google.com/maps/search/?api=1&query={latitude},{longitude}',
                'target': 'new',
            }
        else:
            raise UserError('Invalid coordinates format.')

class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    is_vts_employee = fields.Boolean(readonly=True)
    vts_employee_role = fields.Selection(VTS_EMPLOYEE_ROLES_SELECTION, readonly=True)
    vts_password = fields.Char(readonly=True)
    employee_stock_location = fields.Many2one('stock.location', readonly=True)
    reset_token = fields.Char(readonly=True)
    reset_token_expiry = fields.Datetime(readonly=True)
    reset_password_link = fields.Char(readonly=True)