from odoo import models, api, exceptions, fields, _
from dateutil import parser
from datetime import datetime
import requests

ODOO_DATE_FORMAT = '%Y-%m-%d'
TRACCAR_DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

class FleetTrips(models.Model):
    _name = 'fleet.traccar.trips'
    _description = 'Fleet Trips'

    name = fields.Char('Vehicle')
    device_id = fields.Integer("Device ID")
    device_uid = fields.Char('Unique ID')
    distance = fields.Float('Distance')
    spent_fuel = fields.Float('Spent Fuel')
    distance_in_km = fields.Float(string='Distance(KM)',compute='_get_distance_in_km', store=True)
    average_speed = fields.Float('Average Speed', group_operator=False)
    average_speed_kph = fields.Float('Average Speed(Kph)', group_operator=False,compute='_get_speed_in_kph', store=True)
    max_speed = fields.Float('Maximum Speed', group_operator=False)
    max_speed_kph = fields.Float('Maximum Speed(Kph)', group_operator=False,compute='_get_speed_in_kph', store=True)
    start_time = fields.Datetime('Start Time')
    end_time = fields.Datetime('End Time')
    start_position_id = fields.Integer('Start Position ID')
    end_position_id = fields.Integer('End Position ID')
    start_lat = fields.Char('Start Latitude')
    end_lat = fields.Char('End Latitude')
    start_lon = fields.Char('Start Longitude')
    end_lon = fields.Char('End Longitude')
    start_address = fields.Char('Start Address')
    end_address = fields.Char('End Address')
    duration = fields.Integer('Duration')
    duration_hr = fields.Float('Duration(Hours)',compute='_get_time_in_hours', store=True)
    driver_unique_id = fields.Integer('Integer')
    driver_name = fields.Char('Driver Name')
    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle",required=True)
    company_id = fields.Many2one(related='vehicle_id.company_id', store=True)

    @api.depends('distance')
    def _get_distance_in_km(self):
        for rec in self:
            rec.distance_in_km = rec.distance / 1000
    
    
    @api.depends('duration')
    def _get_time_in_hours(self):
        for rec in self:
            if rec.duration:
                rec.duration_hr = rec.duration / (1000*60*60)
    
    @api.depends('average_speed','max_speed')
    def _get_speed_in_kph(self):
        for rec in self:
            if rec.average_speed:
                rec.average_speed_kph = rec.average_speed * 1.852
            if rec.max_speed:
                rec.max_speed_kph = rec.max_speed * 1.852

    def sync_trips(self, licensePlate=None):
        base_url = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.tracking_base_url')
        api_user = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_user')
        api_password = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_password')
        sync_data = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.sync_data')
        data_start_date = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.data_start_date')

        if licensePlate or sync_data:
            if licensePlate is not None:
                device_records = self.env['fleet.vehicle'].sudo().search([('license_plate', '=', licensePlate)],order='latest_trip_update asc')
            else:
                device_records = self.env['fleet.vehicle'].sudo().search([('is_tracccar_vehicle','=',True)])

            for rec in device_records:
                if rec.traccar_id:
                    dev_id = rec.traccar_id
                    if not rec.latest_trip_update:
                        last_update = self._parse_date_with_z(data_start_date)
                    else:
                        last_update = rec.latest_trip_update.strftime(
                            '%Y-%m-%dT%H:%M:%SZ') if rec.latest_trip_update is not False else datetime.today().strftime(
                            '%Y-%m-%dT%H:%M:%SZ')

                    from_date = last_update if last_update is not None else datetime.today().strftime('%Y-%m-%dT%H:%M:%SZ') 
                    to_date = datetime.today().strftime('%Y-%m-%dT%H:%M:%SZ')
                    params = {'deviceId': dev_id, 'from': from_date, 'to': to_date}
                    trips_response: requests.Response = requests.get(base_url + '/api/reports/trips', params=params,
                                                                    auth=(api_user, api_password))
                    if trips_response.status_code == 200:
                        trips_list = []
                        trips_obj = trips_response.json()
                        for index in range(len(trips_obj)):
                            for key in trips_obj[index]:
                                trip = trips_obj[index]
                                trip_dict = {
                                    "device_id": trip['deviceId'],
                                    "name": trip['deviceName'],
                                    "vehicle_id": rec.id,
                                    "spent_fuel": trip['spentFuel'],
                                    "distance": trip['distance'],
                                    "average_speed": trip['averageSpeed'],
                                    "max_speed": trip['maxSpeed'],
                                    "start_time": self._parse_date(trip['startTime']) if trip['startTime'] is not None else None,
                                    "end_time": self._parse_date(trip['endTime']) if trip['endTime'] is not None else None,
                                    "start_lat": trip['startLat'],
                                    "start_lon": trip['startLon'],
                                    "end_lat": trip['endLat'],
                                    "end_lon": trip['endLon'],
                                    "start_address": trip['startAddress'],
                                    "end_address": trip['endAddress'],
                                    "duration": trip['duration'],
                                    "driver_unique_id": trip['driverUniqueId'],
                                    "driver_name": trip['driverName']
                                }
                            trips_list.append(trip_dict)
                            if rec.latest_trip_update is False:
                                rec.latest_trip_update = self._parse_date(trip['endTime'])
                            rec.latest_trip_update = self._parse_date(trip['endTime']) if datetime.strptime(
                                self._parse_date(trip['endTime']),
                                '%Y-%m-%d %H:%M:%S') > rec.latest_trip_update else rec.latest_trip_update
                        self.create(trips_list)
                        self.env.cr.commit()
                    else:
                        raise exceptions.UserError(trips_response.text + ",Error Code: " + str(trips_response.status_code))

    def _parse_date(self, date):
        formatted_date = (parser.parse(date)).strftime('%Y-%m-%d %H:%M:%S')
        return formatted_date
    
    def _parse_date_with_z(self, date):
        formatted_date = (parser.parse(date)).strftime(TRACCAR_DATE_FORMAT)
        return formatted_date
    
    def open_map(self):
        for record in self:
            if record.start_lat and record.start_lon:
                return {
                    'type': 'ir.actions.act_url',
                    'url': 'https://www.google.com/maps/dir/?api=1&origin=%s,%s&destination=%s,%s' % (record.start_lat,record.start_lon,record.end_lat,record.end_lon),
                    'target': 'new',
                }
