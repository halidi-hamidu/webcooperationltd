import json
import logging

from odoo import http, SUPERUSER_ID
from odoo.http import request

_logger = logging.getLogger(__name__)


class CipsWebhookController(http.Controller):

    @http.route('/cips/webhook', type='http', auth='none', methods=['POST'], csrf=False)
    def cips_webhook(self, **kwargs):
        """
        Endpoint for CIPS webhook callbacks.
        Verifies the HMAC-SHA256 signature before processing.
        Always returns HTTP 200 to acknowledge receipt — errors are logged.
        """
        body = request.httprequest.get_data()
        signature = request.httprequest.headers.get('X-CIPS-Signature', '')
        timestamp = request.httprequest.headers.get('X-CIPS-Timestamp', '')

        # Read the webhook secret from system parameters (Settings > CIPS / Selcom)
        webhook_secret = request.env['ir.config_parameter'].sudo().get_param(
            'custom_ictpack.cips_webhook_secret', default=''
        )

        handler = request.env['cips.webhook.handler'].with_user(SUPERUSER_ID)

        if not handler.verify_hmac(body, signature, timestamp, webhook_secret):
            _logger.warning(
                "CIPS webhook: invalid HMAC signature from %s — "
                "received='%s' secret_configured=%s",
                request.httprequest.remote_addr,
                signature[:20] + '...' if len(signature) > 20 else signature,
                bool(webhook_secret),
            )
            return request.make_response(
                json.dumps({"status": "error", "message": "Invalid signature"}),
                headers=[('Content-Type', 'application/json')],
                status=401,
            )

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            _logger.error("CIPS webhook: invalid JSON payload — %s", str(e))
            return request.make_response(
                json.dumps({"status": "error", "message": "Invalid JSON"}),
                headers=[('Content-Type', 'application/json')],
                status=400,
            )

        event = payload.get('event')
        data = payload.get('data', {})

        _logger.info("CIPS webhook received: event=%s", event)

        if event == 'till_alias.payment_received':
            try:
                handler.handle_till_alias_payment(data)
            except Exception as e:
                # Log the error but always return 200 so CIPS does not retry
                _logger.exception(
                    "CIPS webhook: error processing payment event ref=%s — %s",
                    data.get('gateway_reference'), str(e),
                )

        # Always acknowledge with 200
        return request.make_response(
            json.dumps({"status": "ok"}),
            headers=[('Content-Type', 'application/json')],
        )
