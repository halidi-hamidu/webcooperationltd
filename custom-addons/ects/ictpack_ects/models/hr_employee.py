from odoo import fields, models, api


class ResPartner(models.Model):
    _inherit = 'hr.employee'

    ects_username = fields.Char(related='work_email', string='ECTS Username')
    ects_password = fields.Char('ECTS Password')
    is_ects_employee = fields.Boolean('ECTS Employee')
    is_ects_tagger = fields.Boolean('ECTS Tagger')

    def return_ects_employees(self):
        employees = self.search([('is_ects_employee', '=', True)])

        values = []
        for rec in employees:
            vals = {
                "id": rec.id,
                "name": rec.name,
                "username": rec.ects_username,
                "work_location": rec.work_location_id.name
            }
            values.append(vals)
        return values

class HrWorkLocation(models.Model):
    _inherit = 'hr.work.location'

    is_ects_location = fields.Boolean('ECTS Location')