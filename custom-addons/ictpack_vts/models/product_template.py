from odoo import fields, models, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_vtd_product = fields.Boolean('VTD Product')
    is_vtd_accessory = fields.Boolean('VTD Accessory')
    dispatched_to = fields.Many2one('hr.employee', 'Dispatched To', domain=([('is_vts_employee', '=', True)]))

    def return_vtd_products(self):
        products = self.search([('is_vtd_product', '=', True)])

        values = []
        for rec in products:
            vals = {
                "id": rec.id,
                "name": rec.name,
                "is_vtd_product": rec.is_vtd_product,
                "is_accessory": rec.is_vtd_accessory,
                "price": rec.list_price,
                "dispatched_to": rec.dispatched_to.id,
            }
            values.append(vals)
        return values
