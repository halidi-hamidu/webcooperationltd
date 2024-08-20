from odoo import models, api, exceptions, fields, _
import requests
from dateutil import parser
from datetime import datetime

ODOO_DATE_FORMAT = '%Y-%m-%d'
TRACCAR_DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

class FleetStops(models.Model):
    _name = 'fleet.traccar.stops'
    _description = 'Fleet Stops'

    name = fields.Char('Vehicle')
    device_id = fields.Integer("Device ID")
    start_time = fields.Datetime('Start Time')
    end_time = fields.Datetime('End Time')
    latitude = fields.Char('Latitude')
    longitude = fields.Char('Longitude')
    address = fields.Char('Address')
    duration = fields.Integer('Duration')
    distance = fields.Integer('Duration')
    spent_fuel = fields.Float('Spent Fuel')
    duration_hr = fields.Float('Duration(Hours)',compute='_get_time_in_hours', store=True)
    engine_hours = fields.Integer('Engine Hours')
    engine_hours_hr = fields.Float('Engine Hours',compute='_get_time_in_hours', store=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle',required=True)
    company_id = fields.Many2one(related='vehicle_id.company_id', store=True)

    
    @api.depends('duration','engine_hours')
    def _get_time_in_hours(self):
        for rec in self:
            if rec.duration:
                rec.duration_hr = rec.duration / (1000*60*60)
            if rec.engine_hours:
                rec.engine_hours_hr = rec.engine_hours / (1000*60*60)
    

    def sync_stops(self, licensePlate=None):
        base_url = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.tracking_base_url')
        api_user = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_user')
        api_password = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_password')
        sync_data = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.sync_data')
        data_start_date = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.data_start_date')

        if licensePlate or sync_data:
            if licensePlate is not None:
                device_records = self.env['fleet.vehicle'].sudo().search([('license_plate', '=', licensePlate)],order='latest_stop_update asc')
            else:
                device_records = self.env['fleet.vehicle'].sudo().search([('is_tracccar_vehicle','=',True)])

            for rec in device_records:
                if rec.traccar_id:
                    dev_id = rec.traccar_id

                    if not rec.latest_stop_update:
                        last_update = self._parse_date_with_z(data_start_date)
                    else:
                        last_update = rec.latest_stop_update.strftime(
                            '%Y-%m-%dT%H:%M:%SZ') if rec.latest_stop_update is not False else datetime.today().strftime(
                            '%Y-%m-%dT%H:%M:%SZ')

                    from_date = last_update if last_update is not None else datetime.today().strftime('%Y-%m-%dT%H:%M:%SZ')
                    to_date = datetime.today().strftime('%Y-%m-%dT%H:%M:%SZ')
                    params = {'deviceId': dev_id, 'from': from_date, 'to': to_date}
                    headers = {"Accept" : "application/json"}
                    stops_response = requests.get(base_url + '/api/reports/stops', params=params,headers=headers,
                                                auth=(api_user, api_password))
                    if stops_response.status_code == 200:
                        stops_list = []
                        print(stops_response.url)
                        stops_obj = stops_response.json()
                        for index in range(len(stops_obj)):
                            for key in stops_obj[index]:
                                stop = stops_obj[index]
                                stops_dict = {
                                    "device_id": stop['deviceId'],
                                    "name": stop['deviceName'],
                                    "vehicle_id": rec.id,
                                    "distance": stop['distance'],
                                    "spent_fuel": stop['spentFuel'],
                                    "start_time": self._parse_date(stop['startTime']) if stop['startTime'] is not None else None,
                                    "end_time": self._parse_date(stop['endTime']) if stop['endTime'] is not None else None,
                                    "latitude": stop['latitude'],
                                    "longitude": stop['longitude'],
                                    "duration": stop['duration'],
                                    "engine_hours": stop['engineHours']
                                }
                            stops_list.append(stops_dict)
                            if rec.latest_stop_update is False:
                                rec.latest_stop_update = self._parse_date(stop['endTime'])
                            rec.latest_stop_update = self._parse_date(stop['endTime']) if datetime.strptime(
                                self._parse_date(stop['endTime']),
                                '%Y-%m-%d %H:%M:%S') > rec.latest_stop_update else rec.latest_stop_update
                        self.create(stops_list)
                        self.env.cr.commit()
                    else:
                        raise exceptions.UserError(
                            stops_response.text + ",Error Code: " + str(stops_response.status_code))

    def _parse_date(self, date):
        formatted_date = (parser.parse(date)).strftime('%Y-%m-%d %H:%M:%S')
        return formatted_date
    
    def _parse_date_with_z(self, date):
        formatted_date = (parser.parse(date)).strftime(TRACCAR_DATE_FORMAT)
        return formatted_date
    
    def open_map(self):
        for record in self:
            if record.latitude and record.longitude:
                return {
                    'type': 'ir.actions.act_url',
                    'url': 'https://www.google.com/maps/search/?api=1&query=%s,%s' % (record.latitude,record.longitude),
                    'target': 'new',
                }