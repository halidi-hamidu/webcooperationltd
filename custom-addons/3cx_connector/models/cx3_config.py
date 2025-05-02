from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class ThreeCXConfig(models.Model):
    _name = 'pbx.config'
    _description = '3CX Configuration'

    name = fields.Char('Configuration Name', required=True)
    api_url = fields.Char('3CX API URL', required=True, default='http://localhost:5001')
    webhook_url = fields.Char('Odoo Webhook URL', compute='_compute_webhook_url')
    api_key = fields.Char('API Key', required=True)
    screen_pop_enabled = fields.Boolean('Enable Screen Pop', default=True)
    call_logging_enabled = fields.Boolean('Enable Call Logging', default=True)
    contact_sync_enabled = fields.Boolean('Enable Contact Sync', default=False)
    debug_mode = fields.Boolean('Debug Mode')
    last_sync = fields.Datetime('Last Synchronization')

    @api.depends('name')
    def _compute_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for config in self:
            config.webhook_url = f"{base_url}/3cx/webhook"

    def setup_3cx_webhooks(self):
        self.ensure_one()
        headers = {
            'Authorization': self.api_key,
            'Content-Type': 'application/json'
        }
        webhook_data = {
            "url": self.webhook_url,
            "verb": "POST",
            "contentType": "json",
            "events": [
                {"event": "CallStart"},
                {"event": "CallEnd"},
                {"event": "ContactUpdate"}
            ]
        }
        try:
            response = requests.post(
                f"{self.api_url}/api/Webhooks",
                json=webhook_data,
                headers=headers,
                timeout=10
            )
            if response.status_code == 201:
                return self._show_notification(
                    _('Success'), 
                    _('Webhooks successfully configured'),
                    'success'
                )
            raise UserError(_('Failed to setup webhooks: %s') % response.text)
        except Exception as e:
            _logger.error("3CX Webhook setup failed: %s", str(e))
            raise UserError(_('Error configuring webhooks: %s') % str(e)) from e

    def make_call(self, phone_number):
        self.ensure_one()
        if not phone_number:
            raise UserError(_("Phone number is required"))
        
        headers = {
            'Authorization': self.api_key,
            'Content-Type': 'application/json'
        }
        try:
            response = requests.post(
                f"{self.api_url}/api/Call",
                json={"number": phone_number},
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return self._show_notification(
                    _('Success'),
                    _('Call initiated successfully'),
                    'success'
                )
            raise UserError(_('Call failed: %s') % response.text)
        except requests.exceptions.RequestException as e:
            _logger.error("3CX Call failed: %s", str(e))
            raise UserError(_('Error initiating call: %s') % str(e)) from e

    def sync_contacts(self):
        self.ensure_one()
        if not self.contact_sync_enabled:
            return
            
        # Sync from 3CX to Odoo
        self._sync_from_3cx()
        
        # Sync from Odoo to 3CX
        self._sync_to_3cx()
        
        self.last_sync = fields.Datetime.now()
        return self._show_notification(
            _('Success'),
            _('Contact synchronization completed'),
            'success'
        )

    def _show_notification(self, title, message, type='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': type,
                'sticky': False,
            }
        }
    
    def _sync_to_3cx(self):
        """Sync Odoo contacts to 3CX"""
        partners = self.env['res.partner'].search([
            '|',
            ('phone', '!=', False),
            ('mobile', '!=', False)
        ])
        
        success = 0
        for partner in partners:
            if partner.sync_to_3cx(self):
                success += 1
        
        _logger.info("Synced %d partners to 3CX", success)
        return success

    def _sync_from_3cx(self):
        """Sync contacts from 3CX to Odoo"""
        headers = {'Authorization': self.api_key}
        try:
            response = requests.get(
                f"{self.api_url}/api/Contacts",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                contacts = response.json()
                Partner = self.env['res.partner'].sudo()
                success = 0
                
                for contact in contacts:
                    phone = contact.get('businessphone1') or contact.get('businessphone2')
                    if not phone:
                        continue
                    
                    partner = Partner.search([
                        '|',
                        ('phone', '=', phone),
                        ('mobile', '=', phone),
                        '|',
                        ('cx3_id', '=', contact.get('id')),
                        ('email', '=', contact.get('email'))
                    ], limit=1)

                    vals = {
                        'name': f"{contact.get('firstname', '')} {contact.get('lastname', '')}".strip(),
                        'phone': contact.get('businessphone1', ''),
                        'mobile': contact.get('businessphone2', ''),
                        'email': contact.get('email', ''),
                        'cx3_id': contact.get('id'),
                        'last_cx3_sync': fields.Datetime.now(),
                        'cx3_sync_status': 'synced'
                    }
                    
                    if partner:
                        partner.write(vals)
                    else:
                        Partner.create(vals)
                    success += 1
                
                _logger.info("Synced %d contacts from 3CX", success)
                return success
            else:
                _logger.error("Failed to fetch contacts from 3CX: %s", response.text)
                return 0
        except Exception as e:
            _logger.error("Exception during 3CX sync: %s", str(e))
            return 0
        
    def test_connection(self):
        self.ensure_one()
        headers = {'Authorization': self.api_key}
        try:
            response = requests.get(
                f"{self.api_url}/api/System/Version",
                headers=headers,
                timeout=5
            )
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Connected to 3CX Version: %s') % response.json().get('version'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            raise UserError(_('Connection failed (HTTP %s): %s') % (response.status_code, response.text))
        except Exception as e:
            raise UserError(_('Connection error: %s') % str(e)) from e