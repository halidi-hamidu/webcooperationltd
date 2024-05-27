from odoo import fields, models, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # VFD API Configurations
    vfd_base_url = fields.Char("VFD Base URL", config_parameter='payment_receipt_vfd.vfd_base_url')
    vfd_api_key = fields.Char("VFD API Key", config_parameter='payment_receipt_vfd.vfd_api_key')
    vfd_api_secret = fields.Char("VFD API Secret", config_parameter='payment_receipt_vfd.vfd_api_secret')
    x_tin = fields.Char("TIN Number", config_parameter='payment_receipt_vfd.x_tin')
    vfd_token = fields.Char("VFD Token", config_parameter='payment_receipt_vfd.vfd_token')
    vfd_daily_counter = fields.Integer("VFD Daily Counter", default=0,
                                       config_parameter='payment_receipt_vfd.vfd_daily_counter')
    counter_latest_update = fields.Char("Latest Update", config_parameter='payment_receipt_vfd.counter_latest_update')
    vfd_receipt_count = fields.Integer("Receipt Count", default=0, readonly=True,
                                       config_parameter='payment_receipt_vfd.vfd_receipt_count')

    # VFD Settings
    header = fields.Char('Header', readonly=True, config_parameter='payment_receipt_vfd.header')
    message = fields.Char('Message', readonly=True, config_parameter='payment_receipt_vfd.message')
    expires = fields.Char('Expires', readonly=True, config_parameter='payment_receipt_vfd.expires')
    verification_code = fields.Char('Verification Code', readonly=True,
                                    config_parameter='payment_receipt_vfd.verification_code')
    has_vrn = fields.Boolean('Has VRN', readonly=True, config_parameter='payment_receipt_vfd.has_vrn')

    def refresh_settings(self):
        res, res_obj = self.env['payment.receipt.vfd'].get_vfd_settings()
        if res:
            self.set_param_value('payment_receipt_vfd.header', res['Header'])
            self.set_param_value('payment_receipt_vfd.message', res['Message'])
            self.set_param_value('payment_receipt_vfd.expires', res['Expires'])
            self.set_param_value('payment_receipt_vfd.verification_code', res['VerificationCode'])
            self.set_param_value('payment_receipt_vfd.has_vrn', res['HasVrn'])
            return self.get_notification_success(msg='Settings Refreshed Successful', nt_type='success',
                                         title='Success')
        else:
            return self.get_notification_error(res_obj, title='Error', nt_type='danger')

    def set_param_value(self, key, value):
        self.env['ir.config_parameter'].sudo().set_param(key, value)

    def refresh_token(self):
        res_msg, res = self.env['payment.receipt.vfd'].generate_token()
        if res and res.get('message') is not None:
            notification_error = self.get_notification_error(res, title='Error', nt_type='danger')
            return notification_error
        else:
            notification_success = self.get_notification_success(title='Success', nt_type='success')
            return notification_success

    def get_notification_error(self, res, title, nt_type, msg=None):
        notification_error = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(title),
                'type': nt_type,
                'message': str(res['message']),
                'sticky': False,
            }
        }
        #return notification_error

    def get_notification_success(self, title, nt_type, msg=None):
        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(title),
                'type': nt_type,
                'message': 'Operation Completed successfully',
                'sticky': False,
            }
        }
        #return notification
