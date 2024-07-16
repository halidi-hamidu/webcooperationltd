from odoo import fields, models, api


class StockLot(models.Model):
    _inherit = 'stock.lot'

    ects_assigned_to = fields.Many2one('hr.employee', 'Assigned To')
    ects_state = fields.Selection([
        ('in-stock', 'In Stock'),
        ('dispatched', 'Dispatched'),
        ('for-sale', 'For Sale'),
        ('sold', 'Sold'),
        ('in-transit', 'In Transit'),
        ('unlocked', 'Unlocked'),
        ('to-return', 'To Return')
    ], default='in-stock', string='ECTS State')
    current_move_id = fields.Integer("Current Transfer Id")
    is_ects_product = fields.Boolean(related='product_id.is_ects_product')

    def ects_status(self):
        pass

    def return_assigned_locks(self, employee_id):
        assigned_locks = self.search(
            [('ects_assigned_to', '=', int(employee_id)), ('ects_state', 'in', ['dispatched', 'for-sale'])])

        values = []
        for rec in assigned_locks:
            vals = {
                "id": rec.id,
                "name": rec.name,
                "price": rec.product_id.list_price,
                "assigned_to": rec.id,
                "ects_state": rec.ects_state
            }
            values.append(vals)
        return values
