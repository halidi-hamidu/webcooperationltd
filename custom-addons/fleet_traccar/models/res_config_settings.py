from odoo import fields, api, models, _

class FleetConfiguration(models.TransientModel):
    _inherit = ['res.config.settings']

    tracking_base_url = fields.Char('Traccer URL',config_parameter = 'fleet_traccar.tracking_base_url')
    api_user = fields.Char('Username',config_parameter = 'fleet_traccar.api_user')
    api_password = fields.Char('Password',config_parameter = 'fleet_traccar.api_password')
    sync_data = fields.Boolean("Synchronize Traccar Records", config_parameter = 'fleet_traccar.sync_data')
    import_data = fields.Boolean("Import Vehicle from Traccar", config_parameter = 'fleet_traccar.import_data')
    data_start_date = fields.Datetime("Traccar Data Start Date", default=fields.Date.today(), config_parameter = 'fleet_traccar.data_start_date')