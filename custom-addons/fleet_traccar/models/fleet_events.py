from odoo import api, fields, models, _
from odoo.exceptions import UserError
import requests
from dateutil import parser
from datetime import datetime

ODOO_DATE_FORMAT = '%Y-%m-%d'
TRACCAR_DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

class FleetEvents(models.Model):
    _name = 'fleet.traccar.events'
    _description = 'Fleet Events'

    name = fields.Char('Event Name')
    event_id = fields.Integer('Event Id')
    attributes = fields.Char('Attributes')
    vehicle_id = fields.Many2one('fleet.vehicle')
    device_id = fields.Integer('Device Id')
    geofence_id = fields.Integer('Geofence ID')
    maintenance_id = fields.Integer('Maintanance ID')
    type = fields.Char('Type')
    position_id = fields.Char('Position')
    event_time = fields.Datetime('Event Time')

    def sync_events(self,licensePlate=None):
        base_url = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.tracking_base_url')
        api_user = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_user')
        api_password = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_password')
        sync_data = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.sync_data')
        data_start_date = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.data_start_date')

        if licensePlate or sync_data:
            if licensePlate is not None:
                device_records = self.env['fleet.vehicle'].sudo().search([('license_plate', '=', licensePlate)],order='latest_event_update asc')
            else:
                device_records = self.env['fleet.vehicle'].sudo().search([('is_tracccar_vehicle','=',True)])

            for rec in device_records:
                if rec.traccar_id:
                    dev_id = rec.traccar_id
                    if not rec.latest_event_update:
                        last_update = self._parse_date_with_z(data_start_date)
                    else:
                        last_update = rec.latest_event_update.strftime(
                            '%Y-%m-%dT%H:%M:%SZ') if rec.latest_event_update is not False else datetime.today().strftime(
                            '%Y-%m-%dT%H:%M:%SZ')
                        
                    from_date = last_update if last_update is not None else datetime.today().strftime(
                    '%Y-%m-%dT%H:%M:%SZ') 
                    to_date = datetime.today().strftime('%Y-%m-%dT%H:%M:%SZ')
                    params = {'deviceId': dev_id, 'from': from_date, 'to': to_date}
                    try:
                        events_response: requests.Response = requests.get(base_url + '/api/reports/events', params=params,
                                                                auth=(api_user, api_password))
                        if events_response.status_code == 200:
                            events_list = []
                            events_obj = events_response.json()
                            for index in range(len(events_obj)):
                                for key in events_obj[index]:
                                    event = events_obj[index]
                                    event_dict = {
                                        'event_id': event['id'],
                                        'attributes': event['attributes'],
                                        'vehicle_id': rec.id,
                                        'device_id': event['deviceId'],
                                        'maintenance_id':event['maintenanceId'],
                                        'geofence_id':event['geofenceId'],
                                        'type': event['type'],
                                        'position_id': event['positionId'],
                                        'event_time': self._parse_date(event['eventTime']) if event['eventTime'] is not None else None,
                                    }
                                    events_list.append(event_dict)
                                    if rec.latest_event_update is False:
                                        rec.latest_event_update = self._parse_date(event['eventTime'])
                                    rec.latest_event_update = self._parse_date(event['eventTime']) if datetime.strptime(
                                        self._parse_date(event['eventTime']),
                                        '%Y-%m-%d %H:%M:%S') > rec.latest_event_update else rec.latest_event_update
                            self.create(events_list)
                            self.env.cr.commit()
                    except requests.exceptions.HTTPError as e:
                        raise UserError(("Connection Error " + e))

    def _parse_date_with_z(self, date):
        formatted_date = (parser.parse(date)).strftime(TRACCAR_DATE_FORMAT)
        return formatted_date

    def _parse_date(self, date):
        formatted_date = (parser.parse(date)).strftime('%Y-%m-%d %H:%M:%S')
        return formatted_date