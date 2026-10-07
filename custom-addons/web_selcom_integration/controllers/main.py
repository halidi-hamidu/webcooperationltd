import logging

import werkzeug

from odoo import http
from odoo.http import request

from ..models.exceptions import (
    SelcomValidationException,
    SelcomWebhookException,
)
from ..models.selcom_client import Selcom, SelcomWebhookNotFound

_logger = logging.getLogger(__name__)


class WebSelcomIntegrationController(http.Controller):

    @http.route("/web_selcom/webhook", type="json", auth="public",
                csrf=False, methods=["POST"])
    def selcom_webhook(self, **kwargs):
        """Selcom payment notification endpoint (idempotent)."""
        payload = request.get_json_data() or {}
        selcom = Selcom(request.env)
        try:
            order, status = selcom.handle_webhook(payload)
        except SelcomWebhookNotFound as exc:
            _logger.warning("Selcom webhook for unknown order %s",
                            exc.order_id)
            return {"result": "SUCCESS", "message": "Unknown order logged"}
        except (SelcomValidationException, SelcomWebhookException) as exc:
            _logger.warning("Invalid Selcom webhook: %s", exc)
            return werkzeug.exceptions.BadRequest.description
        return {
            "result": "SUCCESS",
            "message": "Payment notification logged",
            "order_id": order.order_id,
            "status": status,
        }
