from odoo import fields, models, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_ects_product = fields.Boolean('ECTS Product')
    is_master_lock = fields.Boolean('Master Lock')
    ects_state = fields.Selection([
        ('in-stock', 'In Stock'),
        ('dispatched', 'Dispatched'),
        ('for-sale', 'For Sale'),
        ('activated', 'Activated'),
        ('in-transit', 'In Transit'),
        ('unlocked', 'Unlocked'),
        ('to-return', 'To Return')
    ], default='in-stock', string='ECTS State')
    dispatched_to = fields.Many2one('hr.employee', 'Dispatched To', domain=([('is_ects_employee', '=', True)]))

    def return_ects_products(self):
        products = self.search([('is_ects_product', '=', True)])

        values = []
        for rec in products:
            vals = {
                "id": rec.id,
                "name": rec.name,
                "is_master_lock": rec.is_master_lock,
                "price": rec.list_price,
                "ects_state": rec.ects_state,
                "dispatched_to": rec.dispatched_to.id,
            }
            values.append(vals)
        return values
