from odoo import models, api, exceptions, fields
import requests
from dateutil import parser
from datetime import datetime

ODOO_DATE_FORMAT = '%Y-%m-%d'
TRACCAR_DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

class FleetSummary(models.Model):
    _name = 'fleet.traccar.summary'
    _description = 'Fleet Summary'
    _order = 'start_time desc'

    name = fields.Char('Vehicle')
    device_id = fields.Integer("Device ID")
    distance = fields.Float('Distance')
    distance_in_km = fields.Float(string='Distance(KM)', compute='_get_distance_in_km', store=True)
    average_speed = fields.Float('Average Speed', aggregator=False)
    average_speed_kph = fields.Float('Average Speed(Kph)', aggregator=False,compute='_get_speed_in_kph', store=True)
    max_speed = fields.Float('Maximum Speed', aggregator=False)
    max_speed_kph = fields.Float('Maximum Speed(Kph)', aggregator=False,compute='_get_speed_in_kph', store=True)
    start_time = fields.Date('Start Date')
    end_time = fields.Date('End Date')
    spent_fuel = fields.Float('Spent Fuel')
    engine_hours = fields.Integer('Engine Hours')
    engine_hours_hr = fields.Float('Engine Hours',compute='_get_time_in_hours', store=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle')
    company_id = fields.Many2one(related='vehicle_id.company_id', store=True)

    _sql_constraints = [
        ('duplicate_summary_entry', 'unique (start_time,vehicle_id)', 'Daily Summary with the same data exists')
    ]

    start_time_format = "%Y-%m-%dT00:00:00Z"

    @api.depends('distance')
    def _get_distance_in_km(self):
        for rec in self:
            rec.distance_in_km = rec.distance / 1000

    
    @api.depends('engine_hours')
    def _get_time_in_hours(self):
        for rec in self:
            if rec.engine_hours:
                rec.engine_hours_hr = rec.engine_hours / (1000*60*60)
    
    @api.depends('average_speed','max_speed')
    def _get_speed_in_kph(self):
        for rec in self:
            if rec.average_speed:
                rec.average_speed_kph = rec.average_speed * 1.852
            if rec.max_speed:
                rec.max_speed_kph = rec.max_speed * 1.852

    def sync_summary(self, licensePlate=None):
        base_url = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.tracking_base_url')
        api_user = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_user')
        api_password = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_password')
        sync_data = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.sync_data')
        data_start_date = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.data_start_date')

        if licensePlate or sync_data:
            if licensePlate is not None:
                device_records = self.env['fleet.vehicle'].sudo().search([('license_plate', '=', licensePlate)],order='latest_summary_update asc')
            else:
                device_records = self.env['fleet.vehicle'].sudo().search([('is_tracccar_vehicle','=',True)])

            for rec in device_records:
                if rec.traccar_id:
                    dev_id = rec.traccar_id

                    if not rec.latest_summary_update:
                        last_update = self._parse_date_with_z(data_start_date)
                    else:
                        last_update = rec.latest_summary_update.strftime(
                            self.start_time_format) if rec.latest_summary_update is not False else datetime.today().strftime(
                            self.start_time_format)

                    from_date = last_update if last_update is not None else datetime.today().strftime(self.start_time_format)
                    to_date = datetime.today().strftime('%Y-%m-%dT%H:%M:%SZ')
                    params = {'deviceId': dev_id, 'daily': True, 'from': from_date, 'to': to_date}
                    summary_response = requests.get(base_url + '/api/reports/summary', params=params,
                                                    auth=(api_user, api_password))
                    if summary_response.status_code == 200:
                        summary_list = []
                        summary_obj = summary_response.json()
                        summary_obj = list(filter(lambda item: item['startTime'] is not None and item['endTime'] is not None,summary_obj))
                        for index in range(len(summary_obj)):
                            for key in summary_obj[index]:
                                summary = summary_obj[index]
                                summary_dict = {
                                    "device_id": summary['deviceId'],
                                    "name": summary['deviceName'],
                                    "vehicle_id": rec.id,
                                    "distance": summary['distance'],
                                    "average_speed": summary['averageSpeed'],
                                    "max_speed": summary['maxSpeed'],
                                    "start_time": self._parse_date(summary['endTime']) if summary['endTime'] is not None else None,
                                    "end_time": self._parse_date(summary['endTime']) if summary['endTime'] is not None else None,
                                    "engine_hours": summary['engineHours']
                                }
                            summary_list.append(summary_dict)
                            if rec.latest_summary_update is False:
                                rec.latest_summary_update = self._parse_date(summary['endTime'])
                            rec.latest_summary_update = self._parse_date(summary['endTime']) if datetime.strptime(
                                self._parse_date(summary['endTime']),
                                '%Y-%m-%d') > rec.latest_summary_update else rec.latest_summary_update

                        for item in summary_list:
                            rec_exists = self.env[self._name].search(
                                [('start_time', '=', self._parse_date(item['start_time'])),
                                ('vehicle_id', '=', item['vehicle_id'])],
                                limit=1)
                            if rec_exists:
                                rec_exists.write(item)
                                rec_exists.env.cr.commit()
                            else:
                                self.create(item)
                                self.env.cr.commit()
                    else:
                        raise exceptions.UserError(
                            summary_response.text + ",Error Code: " + str(summary_response.status_code))


    def _parse_date(self, date):
        formatted_date = (parser.parse(date)).strftime(ODOO_DATE_FORMAT)
        return formatted_date

    def _parse_date_with_z(self, date):
        formatted_date = (parser.parse(date)).strftime(TRACCAR_DATE_FORMAT)
        return formatted_date

