import json
import logging

from odoo import http
from odoo.http import request

from ..models.exceptions import (
    SelcomValidationException,
    SelcomWebhookException,
)
from ..models.selcom_client import Selcom, SelcomWebhookNotFound

_logger = logging.getLogger(__name__)

WEBHOOK_ENDPOINT = "/selcom-to-webcoop/webhook"
REJECTED_STATUSES = ("amount_mismatch", "currency_mismatch")


class WebSelcomIntegrationController(http.Controller):

    @staticmethod
    def _get_payload():
        """Return the inbound notification as a dict (JSON body, or form
        fields as a fallback)."""
        raw = request.httprequest.get_data(as_text=True) or ""
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except ValueError:
            payload = request.httprequest.form.to_dict()
            if not payload:
                payload = {"raw_body": raw[:5000]}
        return payload if isinstance(payload, dict) else {"data": payload}

    @staticmethod
    def _log_notification(payload):
        """Persist the inbound notification verbatim in selcom.order.response
        before any processing, so it is never lost."""
        order_id = (payload.get("order_id") or payload.get("transid")
                    or "UNKNOWN")
        return request.env["selcom.order.response"].sudo().create({
            "order_id": order_id,
            "endpoint": WEBHOOK_ENDPOINT,
            "direction": "inbound",
            "state": "failed",
            "request_payload": payload,
            "payment_status": payload.get("payment_status")
            or payload.get("status") or payload.get("result"),
            "gateway_reference": payload.get("transid")
            or payload.get("reference"),
            "http_status": 200,
        })

    @http.route(WEBHOOK_ENDPOINT, type="http", auth="public", csrf=False,
                methods=["POST"], save_session=False)
    def selcom_webhook(self, **kwargs):
        """Selcom payment notification endpoint (idempotent).

        1. Save the notification in selcom.order.response.
        2. Process it (update selcom.webhook / mark the order paid).
        3. Update the same log record with the outcome and our reply.
        """
        payload = self._get_payload()
        _logger.info("Selcom webhook received: %s", payload)
        log = self._log_notification(payload)

        http_status = 200
        error = False
        try:
            with request.env.cr.savepoint():
                order, status = Selcom(request.env).handle_webhook(payload)
            reply = {
                "result": "SUCCESS",
                "message": "Payment notification logged",
                "order_id": order.order_id,
                "status": status,
            }
            if status in REJECTED_STATUSES:
                error = "Notification rejected: %s" % status
            log.selcom_webhook_id = order
        except SelcomWebhookNotFound as exc:
            _logger.warning("Selcom webhook for unknown order %s",
                            exc.order_id)
            reply = {"result": "SUCCESS", "message": "Unknown order logged"}
        except (SelcomValidationException, SelcomWebhookException) as exc:
            _logger.warning("Invalid Selcom webhook: %s", exc)
            http_status = 400
            error = str(exc)
            reply = {"result": "FAIL", "message": "Invalid notification"}
        except Exception as exc:  # noqa: BLE001 - never lose the log
            _logger.exception("Selcom webhook processing error")
            http_status = 500
            error = str(exc)
            reply = {"result": "FAIL", "message": "Processing error"}

        log.write({
            "state": "failed" if error else "success",
            "response_payload": reply,
            "error_message": error,
            "http_status": http_status,
        })
        return request.make_json_response(reply, status=http_status)
