from odoo import models, fields
from . utils import format_response


VTD_STATE_SELECTION = [
        ('in-stock', 'In Stock'),
        ('dispatched', 'Dispatched'),
        ('for-sale', 'For Sale'),
        ('sold', 'Sold'),
        ('returned', 'Returned')
    ]

class StockLot(models.Model):
    _inherit = 'stock.lot'

    vtd_dispatched_to = fields.Many2one('hr.employee', 'Dispatched To')
    vtd_state = fields.Selection(VTD_STATE_SELECTION, default='in-stock', string='VTD State', tracking=True)
    current_move_id = fields.Integer("Current Transfer Id")
    is_vtd_product = fields.Boolean(related='product_id.is_vtd_product')
    is_vtd_accessory = fields.Boolean(related='product_id.is_vtd_accessory')


    vtd_dispatched_date = fields.Datetime('Dispatched Date', readonly=True)

    def return_employee_vtds_instock(self, employee_id, domain=[], counter=False):
        # Fetch the employee's stock location
        employee_stock_location = self.env['hr.employee'].search([('id', '=', employee_id)], limit=1).employee_stock_location
    
        # Fetch the stock quants for the employee's stock location
        employee_stock = self.env['stock.quant'].search([('location_id', '=', employee_stock_location.id)] + domain)
    
        # If counter is True, return only counts
        if counter:
            device_count = 0
            accessory_count = 0
            
            for rec in employee_stock:
                if rec.product_id.is_vtd_accessory:
                    accessory_count += rec.quantity
                else:
                    device_count += rec.quantity
            
            return format_response('success', 'Stock count returned successfully.', {
                'device_count': int(device_count),
                'accessory_count': int(accessory_count)
            })
        
        # Aggregate quantities by product
        product_quantities = {}
        for rec in employee_stock:
            product_id = rec.product_id.id
            if product_id in product_quantities:
                product_quantities[product_id]['quantity'] += rec.quantity
                # Add serial/lot number if it exists
                if rec.lot_id and rec.lot_id.name:
                    product_quantities[product_id]['serials'].append({
                        'id': rec.lot_id.id,
                        'name': rec.lot_id.name
                    })
            else:
                product_quantities[product_id] = {
                    "id": rec.id,
                    "name": rec.product_id.name,
                    "quantity": rec.quantity,
                    "type": 'Device' if rec.product_id.is_vtd_accessory is False else 'Accessory',
                    "serials": [{'id': rec.lot_id.id, 'name': rec.lot_id.name}] if rec.lot_id and rec.lot_id.name else []
                }
    
        # Convert the aggregated data into a list
        values = list(product_quantities.values())
    
        return format_response('success', 'Device in stock returned successfully.', values)


    def return_assigned_vtd(self, employee_id, domain=[]):
        assigned_locks = self.search(
            [
                ('vtd_dispatched_to', '=', int(employee_id)),
                ('vtd_state', '=', 'for-sale'),
            ]
            + domain
        )

        values = []
        for rec in assigned_locks:
            vals = {
                "id": rec.id,
                "name": rec.name,
                "assigned_to": rec.id,
                "vtd_state": rec.vtd_state,
                "vtd_state_desc": dict(VTD_STATE_SELECTION).get(rec.vtd_state, '-'),
                "product": rec.product_id.name,
            }
            values.append(vals)
        return values
