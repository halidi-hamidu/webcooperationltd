# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    joining_date = fields.Date(readonly=True)
    id_expiry_date = fields.Date(readonly=True)
    passport_expiry_date = fields.Date(readonly=True)
