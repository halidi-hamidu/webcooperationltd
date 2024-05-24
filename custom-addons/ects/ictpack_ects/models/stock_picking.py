from odoo import fields, models, api
import requests
import json


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    ects_state = fields.Selection([
        ('in-stock', 'In Stock'),
        ('dispatched', 'Dispatched'),
        ('for-sale', 'For Sale'),
    ], default='in-stock', string='ECTS State', tracking=True)
    dispatched_to = fields.Many2one('hr.employee', 'Dispatched To', domain=([('is_ects_employee', '=', True)]))
    is_ects_transfer = fields.Boolean('ECTS Tranfer?')
    is_device_return = fields.Boolean('Device Return?')

    def ects_status(self):
        pass

    def button_validate(self):
        # Update Lots With current Transfer(stock picking) and current assigned id
        res = super(StockPicking, self).button_validate()
        if res:
            for rec in self:
                if rec.is_ects_transfer:
                    rec.ects_state = 'dispatched'
                    for line in rec.move_line_ids_without_package:
                        lot = self.env['stock.lot'].search([('id', '=', line.lot_id.id)])
                        lot.ects_assigned_to = rec.dispatched_to
                        lot.ects_state = 'dispatched'
                        lot.current_move_id = rec.id
                        device_serials = [int(lot.name)]
                        self.activate_device_in_middleware(device_serials)

                if rec.is_device_return:
                    rec.ects_state = 'in-stock'
                    for line in rec.move_line_ids_without_package:
                        lot = self.env['stock.lot'].search([('id', '=', line.lot_id.id)])
                        lot.ects_assigned_to = False
                        lot.ects_state = 'in-stock'
                        lot.current_move_id = rec.id
        return res

    def activate_device_in_middleware(self, device_serials):
        api_url = "http://102.214.30.62:5000/api/v1/device/activate"
        try:
            response = requests.post(api_url, json=device_serials)
            if response.status_code == 200:
                json_data = response.json()
                if json_data.get("success") == 1:
                    print("Activated in middleware:" + str(device_serials))
                    return True
                else:
                    print(f"Error: {json_data.get('message')}")
                    return False
            else:
                print(f"Error: {response.status_code} - {response.reason}")
                return False
        except requests.RequestException as e:
            print(f"Request Error: {e}")
            return False

    def return_transfer_batch(self, employee_id):
        batches = self.env['stock.picking'].search(
            [('dispatched_to', '=', int(employee_id)), ('is_ects_transfer', '=', True),
             ('ects_state', '=', 'dispatched')])

        values = []
        for rec in batches:
            vals = {
                "id": rec.id,
                "name": rec.name,
                "date": rec.date_done,
                "assigned_to": rec.dispatched_to,
                "ects_state": rec.ects_state
            }
            values.append(vals)
        return values

    def confirm_locks_receipt(self, transfer_id):
        pass
        # batch = self.browse(int(transfer_id))
        # batch.ects_state = 'for-sale'
        # for line in batch.move_line_ids_without_package:
        #     lot = self.env['stock.lot'].search([('id', '=', line.lot_id.id), ('ects_state', '=', 'dispatched')])
        #     lot.ects_state = 'for-sale'


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    type_code = fields.Char('Type Code')
