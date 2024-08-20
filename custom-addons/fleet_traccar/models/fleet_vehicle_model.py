from odoo import fields, models, api


class ModelName(models.Model):
    _inherit = 'fleet.vehicle.model'

    manufacturer_cons_rate = fields.Float("Manufacturer Fuel Consumption Rate/(KM/Hr)")