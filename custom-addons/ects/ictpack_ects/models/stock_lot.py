from odoo import fields, models, api
import requests
import logging
from dateutil import parser
from datetime import datetime
from pytz import timezone,utc

_logger = logging.getLogger(__name__)


class StockLot(models.Model):
    _inherit = 'stock.lot'

    ects_assigned_to = fields.Many2one('hr.employee', 'Assigned To')
    ects_state = fields.Selection([
        ('in-stock', 'In Stock'),
        ('dispatched', 'Dispatched'),
        ('for-sale', 'For Sale'),
        ('sold', 'Sold'),
        ('in-transit', 'In Transit'),
        ('unlocked', 'Trip End'),
        ('to-return', 'To Return')
    ], default='in-stock', string='ECTS State', tracking=True)
    current_move_id = fields.Integer("Current Transfer Id")
    is_ects_product = fields.Boolean(related='product_id.is_ects_product')
    tra_status = fields.Char('Status')
    tra_date = fields.Datetime('Last Update')
    tra_power = fields.Float('Power')
    longitude = fields.Char('Longitude')
    latitude = fields.Char('Latitude')

    ###### Trip Details
    trip_count = fields.Integer(string="Trip Count", compute='_get_trips',store=True)
    trip_ids = fields.One2many(
        comodel_name='ects.trip',
        inverse_name='e_seal_id',
        string="Trips",
        compute='_get_trips',
        copy=False)
    

    @api.depends('ects_state')
    def _get_trips(self):
        for seal in self:
            trips = self.env['ects.trip'].search([('e_seal_id','=',seal.name)])
            seal.trip_ids = trips
            seal.trip_count = len(trips)

    def action_view_trip(self):
        trips = self.trip_ids
        action = self.env['ir.actions.actions']._for_xml_id('ictpack_ects.ects_trip_act_window')
        if len(trips) > 1:
            action['domain'] = [('id', 'in', trips.ids)]
        elif len(trips) == 1:
            form_view = [(self.env.ref('ects_trip_form_view').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state,view) for state,view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = trips.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action

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

    def return_sold_locks(self, employee_id):
        assigned_locks = self.search(
            [('ects_assigned_to', '=', int(employee_id)), ('ects_state', '=', 'sold')])

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

    def get_device_status(self, device_id):
        api_url = f"http://102.214.30.62:5000/api/v1/device/status/{device_id}"
        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                json_data = response.json()
                _id, deviceSerial, status, date, power, longitude, latitude, tripNumber = json_data.values()
                return _id, deviceSerial, status, date, power, longitude, latitude, tripNumber
            else:
                _logger.error(f"Error: {response.status_code} - {response.reason}")
                return None
        except requests.RequestException as e:
            _logger.error(f"Request Error: {e}")
            return None

    # Refresh Device Status:
    def refresh_device_status(self):
        devices = self.search([])
        for device in devices:
            device_id = device.name
            if self.get_device_status(device_id) is not None:
                _id, deviceSerial, status, date, power, longitude, latitude, tripNumber = self.get_device_status(
                    device_id)
            else:
                _id = None
            if _id is not None:
                # for rec in device:
                device.tra_status = status
                device.tra_date = self._parse_date(date)
                device.tra_power = power
                device.longitude = longitude
                device.latitude = latitude

                if device.tra_status == 'IN TRANSIT' and device.ects_state != 'in-transit':
                    device.ects_state = 'in-transit'
                    for trip in device.trip_ids:
                        if trip.state == 'approved' or trip.state == 'issued':
                            trip.state = 'in-transit'
                    try:
                        device.env['ects.trip'].activate_device(device.name)
                        device.env.cr.commit()
                    except Exception as e:
                        _logger.error("Error Refreshing Device: " + str(device.name) + ":" + str(e))
                elif device.tra_status == 'IDLE' and device.ects_state == 'in-transit':
                    device.ects_state = 'unlocked'
                    for trip in device.trip_ids:
                        if trip.state == 'in-transit':
                            trip.state = 'unlocked'
                    device.env.cr.commit()
            else:
                _logger.error(device_id + ":Failed to retrieve device status.")

    def _parse_date(self, date):
        tz = timezone('Africa/Dar_es_Salaam')
        formatted_date = (parser.parse(date)).strftime('%Y-%m-%d %H:%M:%S')
        datetime_obj = datetime.strptime(formatted_date, "%Y-%m-%d %H:%M:%S")
        localized_time = tz.localize(datetime_obj)
        utc_datetime = localized_time.astimezone(utc)
        formatted_utc_time = utc_datetime.strftime('%Y-%m-%d %H:%M:%S')
        return formatted_utc_time
    
    def open_map(self):
        for record in self:
            if record.latitude and record.longitude:
                return {
                    'type': 'ir.actions.act_url',
                    'url': 'https://www.google.com/maps/search/?api=1&query=%s,%s' % (record.latitude,record.longitude),
                    'target': 'new',
                }