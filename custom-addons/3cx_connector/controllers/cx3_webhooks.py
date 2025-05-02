from odoo import http
from odoo.http import request
from odoo import models, fields, api, _
import json
import logging

_logger = logging.getLogger(__name__)

class ThreeCXWebhookController(http.Controller):

    @http.route('/3cx/webhook', type='json', auth='none', csrf=False)
    def handle_webhook(self):
        data = request.jsonrequest
        _logger.debug("3CX Webhook received: %s", data)

        config = request.env['pbx.config'].sudo().search([], limit=1)
        if not config:
            _logger.error("No 3CX configuration found")
            return {'status': 'error', 'message': 'Configuration missing'}

        try:
            if data.get('event') == 'CallStart':
                return self._handle_call_start(config, data.get('call', {}))
            elif data.get('event') == 'CallEnd':
                return self._handle_call_end(config, data.get('call', {}))
            elif data.get('event') == 'ContactUpdate':
                return self._handle_contact_update(config, data.get('contact', {}))
            return {'status': 'ignored', 'message': 'Unknown event type'}
        except Exception as e:
            _logger.error("Webhook processing failed: %s", str(e))
            return {'status': 'error', 'message': str(e)}

    def _handle_call_start(self, config, call_data):
        if not config.screen_pop_enabled:
            return {'status': 'disabled'}

        phone = call_data.get('number') or call_data.get('callerNumber')
        partner = request.env['res.partner'].sudo().search([
            '|',
            ('phone', '=', phone),
            ('mobile', '=', phone)
        ], limit=1)

        if partner:
            return {
                'status': 'success',
                'partner': {
                    'id': partner.id,
                    'name': partner.name,
                    'phone': partner.phone,
                    'mobile': partner.mobile,
                    'email': partner.email,
                    'company': partner.parent_id.name if partner.parent_id else '',
                    'redirect_url': f"/web#id={partner.id}&model=res.partner&view_type=form"
                }
            }
        return {'status': 'not_found'}

    def _handle_call_end(self, config, call_data):
        if not config.call_logging_enabled:
            return {'status': 'disabled'}

        phone = call_data.get('number') or call_data.get('callerNumber')
        partner = request.env['res.partner'].sudo().search([
            '|',
            ('phone', '=', phone),
            ('mobile', '=', phone)
        ], limit=1)

        request.env['call.log'].sudo().create({
            'partner_id': partner.id if partner else None,
            'phone': phone,
            'direction': 'in' if call_data.get('incoming') else 'out',
            'start_time': call_data.get('startTime'),
            'end_time': call_data.get('endTime'),
            'status': 'answered' if call_data.get('answered') else 'missed',
            'recording_url': call_data.get('recordingUrl'),
        })
        return {'status': 'logged'}

    def _handle_contact_update(self, config, contact_data):
        if not config.contact_sync_enabled:
            return {'status': 'disabled'}
        # Contact sync implementation here
        return {'status': 'success'}
    
    def _handle_contact_update(self, config, contact_data):
        """Handle contact updates from 3CX"""
        if not config.contact_sync_enabled:
            return {'status': 'disabled'}

        Partner = request.env['res.partner'].sudo()
        phone = contact_data.get('businessphone1') or contact_data.get('businessphone2')
        
        if not phone:
            return {'status': 'error', 'message': 'No phone number provided'}

        partner = Partner.search([
            '|',
            ('phone', '=', phone),
            ('mobile', '=', phone),
            '|',
            ('cx3_id', '=', contact_data.get('id')),
            ('email', '=', contact_data.get('email'))
        ], limit=1)

        vals = {
            'name': f"{contact_data.get('firstname', '')} {contact_data.get('lastname', '')}".strip(),
            'phone': contact_data.get('businessphone1', ''),
            'mobile': contact_data.get('businessphone2', ''),
            'email': contact_data.get('email', ''),
            'cx3_id': contact_data.get('id'),
            'last_cx3_sync': fields.Datetime.now(),
            'cx3_sync_status': 'synced'
        }

        if partner:
            partner.write(vals)
            return {'status': 'updated', 'partner_id': partner.id}
        else:
            new_partner = Partner.create(vals)
            return {'status': 'created', 'partner_id': new_partner.id}