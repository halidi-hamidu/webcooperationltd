from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    vrn = fields.Char(string='VRN', default=False, copy=False, )
