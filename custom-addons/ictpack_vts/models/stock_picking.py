from odoo import fields, models, api
import requests
import json
from .utils import format_response

VTD_STATE_SELECTION = [
    ('in-stock', 'In Stock'),
    ('dispatched', 'Dispatched'),
    ('for-sale', 'For Sale'),
]

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    vtd_state = fields.Selection(VTD_STATE_SELECTION, default='in-stock', string='VTD State', tracking=True)
    dispatched_to = fields.Many2one('hr.employee', 'Dispatched To', domain=([('is_vts_employee', '=', True)]))
    is_vtd_transfer = fields.Boolean('VTD Tranfer?')

    def button_validate(self):
        """
        Validate the stock picking and update the VTD state and information if it is a VTD transfer.

        :return: The result of the super method button_validate.
        """
        res = super(StockPicking, self).button_validate()
        if self.is_vtd_transfer:
            self.vtd_state = 'dispatched'
            for line in self.move_line_ids_without_package:
                lot = self.env['stock.lot'].search([('id', '=', line.lot_id.id)])
                lot.vtd_dispatched_to = self.dispatched_to
                lot.vtd_state = 'dispatched'
                lot.vtd_dispatched_date = fields.datetime.now()
                lot.current_move_id = self.id

        return res

    def confirm_receiving_batch(self, transfer_id):
        """
        Confirm the receiving of a batch.
        Args:
            transfer_id (int): The ID of the transfer.
        Returns:
            bool: True if the receiving is confirmed successfully, False otherwise.
        """
        # Rest of the code...
        batch = self.browse(int(transfer_id))
        batch.vtd_state = 'for-sale'
        for line in batch.move_line_ids_without_package:
            lots = self.env['stock.lot'].search([('id', '=', line.lot_id.id), ('vtd_state', '=', 'dispatched')])
            lots.write({'vtd_state': 'for-sale'})

        return format_response('success', 'Receiving batch confirmed successfully.', True)

    def return_transfer_batch(self, employee_id):
        """
        Retrieve a list of transfer batches based on the given employee ID.
        Args:
            employee_id (int): The ID of the employee.
        Returns:
            list: A list of dictionaries containing information about each transfer batch.
        """
        batches = self.env['stock.picking'].search(
            [('dispatched_to', '=', int(employee_id)), ('is_vtd_transfer', '=', True),
             ('vtd_state', '=', 'dispatched')], order='date_done desc')

        values = []
        values = []
        for rec in batches:
            vtd_serial_ids = [line.lot_id.name for line in rec.move_line_ids_without_package if line.lot_id.name]
            vtd_serial_count = len(vtd_serial_ids)
            vtd_accessories = [{'product': product.product_id.name, 'quantity': product.qty_done} for product in rec.move_line_ids_without_package if product.product_id.is_vtd_accessory]

            vals = {
                "id": rec.id,
                "name": rec.name,
                "date": rec.date_done,
                "dispatched_to": rec.dispatched_to.name,
                "vtd_state": rec.vtd_state,
                'vtd_state_desc': dict(VTD_STATE_SELECTION)[rec.vtd_state],
                "vtd_serial_ids": vtd_serial_ids,
                "vtd_serial_count": vtd_serial_count,
                "vtd_accessories": vtd_accessories
            }
            values.append(vals)
        return format_response('success', "Transfer batch returned successfully.", values)
        

        