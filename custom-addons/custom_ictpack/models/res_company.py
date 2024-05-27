from odoo import models, fields, api, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    vrn = fields.Char(string='VRN', default=False, copy=False, )
