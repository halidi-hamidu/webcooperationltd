# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import requests
import json
from odoo.exceptions import UserError

from dateutil import parser

ODOO_DATE_FORMAT = '%Y-%m-%d'
TRACCAR_DATE_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    device_uid = fields.Char('Device Unique Identifier',)
    traccar_id = fields.Integer('External Traccar ID')
    event_lines_id = fields.One2many('fleet.traccar.events', 'vehicle_id')
    latest_device_update = fields.Datetime('Device latest update time')
    trip_ids = fields.One2many('fleet.traccar.trips', 'vehicle_id')
    stop_ids = fields.One2many('fleet.traccar.stops', 'vehicle_id')
    summary_ids = fields.One2many('fleet.traccar.summary', 'vehicle_id')
    latest_trip_update = fields.Datetime("Latest Trip updates")
    latest_stop_update = fields.Datetime("Latest Stop updates")
    latest_summary_update = fields.Datetime("Latest Summary updates")
    latest_event_update = fields.Datetime("Latest Event updates")
    manufacturer_cons_rate = fields.Float(related='model_id.manufacturer_cons_rate', readonly=True)
    is_tracccar_vehicle = fields.Boolean('Tracked in Traccar',default=False)
    traccar_status = fields.Boolean("Vehicle Status", default=False)
    create_traccer_vehicle = fields.Boolean("Create in Traccar Status", default=False)
    imported_vehicle = fields.Boolean("Imported vehicle", default=False)

    _vehicle_license_plate = models.Constraint('unique (license_plate)', 'The Vehicle with this License plate already exists')

    @api.model
    @api.depends('license_plate')
    def _compute_vehicle_name(self):
        for record in self:
            record.name = (record.license_plate or _('No Plate'))


    def import_devices(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.tracking_base_url')
        api_user = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_user')
        api_password = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_password')
        vehicle_model = self.env.ref('fleet_traccar.model_traccar')
        import_data = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.import_data')

        if import_data:
            devices_response = requests.get(base_url + '/api/devices', auth=(api_user, api_password))
            if devices_response.status_code == 200:
                devices_obj = devices_response.json()
                vehicles_list = []
                for index in range((len(devices_obj))):
                    for key in devices_obj:
                        vals = {
                            'model_id': vehicle_model.id,
                            'is_tracccar_vehicle': True,
                            'imported_vehicle': True,
                            'traccar_id': devices_obj[index]['id'],
                            'license_plate': devices_obj[index]['name'],
                            'device_uid': devices_obj[index]['uniqueId'],
                        }
                        license_plate = self.search(['|', ('license_plate', '=', devices_obj[index]['name']),
                                                    ('traccar_id', '=', devices_obj[index]['id'])])
                    
                    if not license_plate:
                        vehicles_list.append(vals)
                    else:
                        license_plate.write(vals)
                self.create(vehicles_list)

    def sync_devices(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.tracking_base_url')
        api_user = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_user')
        api_password = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_password')
        sync_data = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.sync_data')

        if sync_data:
            devices_response = requests.get(base_url + '/api/devices', auth=(api_user, api_password))
            if devices_response.status_code == 200:
                devices_obj = devices_response.json()
                for index in range((len(devices_obj))):
                    for key in devices_obj:
                        vals = {
                            'traccar_id': devices_obj[index]['id'],
                            'license_plate': devices_obj[index]['name'],
                            'device_uid': devices_obj[index]['uniqueId'],
                            'traccar_status': True if devices_obj[index]['status'] == 'online' else False,
                            'latest_device_update': self._parse_date(devices_obj[index]['lastUpdate']) if devices_obj[index]['lastUpdate'] is not None else None
                        }
                        license_plate = self.search(['|', ('license_plate', '=', devices_obj[index]['name']),
                                                    ('traccar_id', '=', devices_obj[index]['id'])])
                    if license_plate:
                        license_plate.write(vals)

    def sync_single_trip(self):
        self.env['fleet.traccar.trips'].sync_trips(self.license_plate)

    def sync_single_stop(self):
        self.env['fleet.traccar.stops'].sync_stops(self.license_plate)

    def sync_single_summary(self):
        self.env['fleet.traccar.summary'].sync_summary(self.license_plate)

    def sync_single_event(self):
        self.env['fleet.traccar.events'].sync_events(self.license_plate)

    @api.model
    def create(self, vals_list):
        res = super(FleetVehicle, self).create(vals_list)
        if res:
            if res.is_tracccar_vehicle and res.create_traccer_vehicle and not res.imported_vehicle:
                for rec in res:
                    base_url = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.tracking_base_url')
                    api_user = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_user')
                    api_password = self.env['ir.config_parameter'].sudo().get_param('fleet_traccar.api_password')
                    json_data = {
                        "attributes": {},
                        "name": rec.license_plate,
                        "uniqueId": rec.device_uid,
                        "status": "offline",
                        "lastUpdate": None,
                        "positionId": 0,
                        "geofenceIds": [],
                        "phone": "",
                        "model":rec.model_id.name,
                        "contact": "",
                        "category": "",
                        "disabled": False,
                    }
                    try:
                        response = requests.post(base_url + '/api/devices', auth=(api_user, api_password), json=json_data)
                        if response.status_code == 200:
                            data = json.loads(response.text)
                            rec.write({'traccar_id': data['id']})
                        else:    
                            raise UserError(
                                "Response Status: " + str(
                                    response.status_code) + "\n" + "Response Error Text: " + response.text + "\n" )
                        
                    except requests.exceptions.HTTPError as e:
                        raise UserError(("Connection Error " + e))
        return res
    
    def _parse_date(self, date):
        formatted_date = (parser.parse(date)).strftime(ODOO_DATE_FORMAT)
        return formatted_date