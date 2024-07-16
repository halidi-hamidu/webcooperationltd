from odoo import fields, models, api


class SMSGateway(models.Model):
    _name = 'sms.notification.gateway'
    _description = 'SMS Notification Gateway'

    name = fields.Char("Gateway Name")
    base_url = fields.Char("Gateway Base URL")
    api_user = fields.Char("API User")
    api_token = fields.Char("API Token", password=True)
    api_user_password = fields.Char("API User Password", password=True)
    api_channel = fields.Char("API Channel")
    active = fields.Boolean('Active')
