from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import requests

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    call_log_ids = fields.One2many('call.log', 'partner_id', string='Call History')
    call_log_count = fields.Integer(compute='_compute_call_log_count', string='Call Count')
    cx3_id = fields.Char('3CX Contact ID')
    last_cx3_sync = fields.Datetime('Last 3CX Sync')
    cx3_sync_status = fields.Selection([
        ('synced', 'Synced'),
        ('pending', 'Pending'),
        ('error', 'Error')
    ], string='Sync Status')

    def _compute_call_log_count(self):
        for partner in self:
            partner.call_log_count = self.env['call.log'].search_count([
                ('partner_id', '=', partner.id)
            ])

    def action_open_call_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Call History'),
            'res_model': 'call.log',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {
                'default_partner_id': self.id,
                'search_default_group_by_partner': 1
            },
            'target': 'current',
        }

    def action_make_call(self):
        self.ensure_one()
        if not (self.phone or self.mobile):
            raise UserError(_("No phone number available for this contact"))
        
        phone = self.phone or self.mobile
        config = self.env['pbx.config'].search([], limit=1)
        if not config:
            raise UserError(_("3CX configuration not found"))
        
        return config.make_call(phone)

    def find_partner_by_phone(self, phone):
        """Find partner by phone number (mobile or phone)"""
        return self.search([
            '|',
            ('phone', '=', phone),
            ('mobile', '=', phone)
        ], limit=1)

    def sync_to_3cx(self, config):
        """Sync partner data to 3CX"""
        self.ensure_one()
        if not (self.phone or self.mobile):
            return False

        contact_data = {
            "firstname": self.firstname or self.name.split()[0],
            "lastname": self.lastname or " ".join(self.name.split()[1:]),
            "email": self.email or "",
            "businessphone1": self.phone or "",
            "businessphone2": self.mobile or "",
            "company": self.parent_id.name if self.parent_id else ""
        }

        try:
            if self.cx3_id:
                # Update existing contact
                response = requests.put(
                    f"{config.api_url}/api/Contacts/{self.cx3_id}",
                    json=contact_data,
                    headers={'Authorization': config.api_key},
                    timeout=10
                )
            else:
                # Create new contact
                response = requests.post(
                    f"{config.api_url}/api/Contacts",
                    json=contact_data,
                    headers={'Authorization': config.api_key},
                    timeout=10
                )
                if response.status_code == 201:
                    self.cx3_id = response.json().get('id')

            if response.status_code in [200, 201]:
                self.write({
                    'last_cx3_sync': fields.Datetime.now(),
                    'cx3_sync_status': 'synced'
                })
                return True
            else:
                self.cx3_sync_status = 'error'
                _logger.error("3CX Sync Error: %s", response.text)
                return False
        except Exception as e:
            self.cx3_sync_status = 'error'
            _logger.error("3CX Sync Exception: %s", str(e))
            return False