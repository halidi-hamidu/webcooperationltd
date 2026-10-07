"""Core Selcom API client.

All Selcom endpoints are encapsulated here in a single service class so no
API/signing logic is duplicated elsewhere. Configuration comes from
ir.config_parameter (never hard-coded).
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone

import requests

from .exceptions import (
    SelcomApiException,
    SelcomAuthenticationException,
    SelcomOrderException,
    SelcomTimeoutException,
    SelcomValidationException,
)

_logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
SUCCESS_CODE = "000"

# Centralized Selcom payment status -> application status mapping
STATUS_MAP = {
    "PENDING": "pending",
    "INPROGRESS": "processing",
    "COMPLETED": "paid",
    "CANCELLED": "cancelled",
    "USERCANCELLED": "cancelled",
    "REJECTED": "failed",
}


class Selcom:
    """Central Selcom service: credentials, signing, requests, endpoints."""

    def __init__(self, env):
        """env: an Odoo Environment. Credentials are read from
        ir.config_parameter so nothing is ever hard-coded."""
        icp = env["ir.config_parameter"].sudo()
        self.api_key = icp.get_param("web_selcom_integration.api_key", "")
        self.api_secret = icp.get_param("web_selcom_integration.api_secret", "")
        self.base_url = (icp.get_param(
            "web_selcom_integration.base_url",
            "https://selcom-payment-api.akamilab.com/v1") or "").rstrip("/")
        self.vendor = icp.get_param("web_selcom_integration.vendor_till", "")
        self.env = env
        if not (self.api_key and self.api_secret and self.vendor):
            _logger.warning("Selcom credentials not fully configured")

    # ------------------------------------------------------------------
    # URL Base64 helpers
    # ------------------------------------------------------------------
    @staticmethod
    def encode_url(url):
        if not url:
            return ""
        return base64.b64encode(url.encode("utf-8")).decode("ascii")

    @staticmethod
    def decode_url(encoded):
        if not encoded:
            return ""
        try:
            return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
        except Exception:
            # Not valid base64 — assume it was already a plain URL.
            return encoded

    # ------------------------------------------------------------------
    # Payment status mapping
    # ------------------------------------------------------------------
    @staticmethod
    def map_payment_status(selcom_status):
        return STATUS_MAP.get((selcom_status or "").upper(), "pending")

    # ------------------------------------------------------------------
    # Order ID generation
    # ------------------------------------------------------------------
    @staticmethod
    def generate_order_id():
        return "ORD-%s-%s" % (
            datetime.now(timezone.utc).strftime("%Y%m%d"),
            secrets.token_hex(3).upper(),
        )

    # ------------------------------------------------------------------
    # Signing / requests
    # ------------------------------------------------------------------
    def _signed_headers(self, method, path, payload=None, digest_ts=None):
        """Build Selcom digest auth headers:
        Digest apikey + Bearer secret + HMAC-SHA256 signature."""
        timestamp = digest_ts or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        signed_fields = "timestamp=%s" % timestamp
        body = json.dumps(payload or {}, sort_keys=True,
                          separators=(",", ":"))
        digest = hmac.new(
            self.api_secret.encode("utf-8"),
            body.encode("utf-8"), hashlib.sha256).hexdigest()
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            ("%s%s%s%s%s" % (self.api_key, timestamp, digest, method,
                             path)).encode("utf-8"),
            hashlib.sha256).hexdigest()
        return {
            "Authorization": "SELCON %s" % signature,
            "Digest-Username": self.api_key,
            "Digest-Timestamp": timestamp,
            "Digest": digest,
            "Signed-Fields": signed_fields,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }

    def _make_request(self, method, path, payload=None, params=None):
        """Single HTTP entry point for every Selcom endpoint."""
        url = self.base_url + path
        if params:
            # DELETE/GET params become signed query string
            query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            path = f"{path}?{query}"
            url = self.base_url + path
            payload = dict(params)
        headers = self._signed_headers(method, path, payload)
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
            elif method == "DELETE":
                resp = requests.delete(url, headers=headers,
                                       timeout=DEFAULT_TIMEOUT)
            else:
                resp = requests.post(url, headers=headers,
                                     data=json.dumps(payload or {}),
                                     timeout=DEFAULT_TIMEOUT)
        except requests.Timeout as exc:
            raise SelcomTimeoutException(
                "Selcom request timed out", endpoint=path) from exc
        except requests.RequestException as exc:
            raise SelcomApiException(
                "Selcom request failed: %s" % exc.__class__.__name__,
                endpoint=path) from exc

        if resp.status_code in (401, 403):
            raise SelcomAuthenticationException(
                "Selcom authentication failed", endpoint=path,
                http_status=resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            data = {"resultcode": str(resp.status_code), "result": "ERROR",
                    "message": resp.text[:200]}
        if resp.status_code >= 400 or data.get("resultcode") != SUCCESS_CODE:
            _logger.error("Selcom API error on %s: http=%s code=%s",
                          path, resp.status_code, data.get("resultcode"))
            raise SelcomApiException(
                data.get("message", "Selcom API error"),
                endpoint=path, http_status=resp.status_code,
                result_code=data.get("resultcode"))
        _logger.info("Selcom %s succeeded (ref=%s)", path,
                     data.get("reference"))
        return data

    @staticmethod
    def _handle_response(data):
        """Normalize a success payload; decode gateway URL in data items."""
        items = data.get("data") or []
        decoded = []
        for item in items:
            item = dict(item)
            if "payment_gateway_url" in item:
                item["payment_gateway_url"] = Selcom.decode_url(
                    item["payment_gateway_url"])
            decoded.append(item)
        data["data"] = decoded
        return data

    # ------------------------------------------------------------------
    # Till alias
    # ------------------------------------------------------------------
    def generate_till_alias(self, customer_id, existing=None):
        """Return an existing alias if present, else build a unique one.

        Uniqueness is enforced by res.partner.selcom_till_alias's unique
        SQL constraint (safe under concurrency: the second write raises
        IntegrityError and the caller can retry).
        """
        if existing:
            return existing
        partner = self.env["res.partner"].sudo().browse(customer_id)
        if partner.selcom_till_alias:
            return partner.selcom_till_alias
        return "CUST-%s-%s" % (customer_id, secrets.token_hex(4).upper())

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    def create_order(self, order):
        """POST /v1/checkout/create-order — full order (card-capable).
        `order` must be a dict (SelcomOrderRequest payload)."""
        required = ("order_id", "buyer_email", "buyer_name", "buyer_phone",
                    "amount", "currency")
        missing = [f for f in required if not order.get(f)]
        if missing:
            raise SelcomValidationException(
                "Missing required fields: %s" % ", ".join(missing),
                endpoint="create-order")
        payload = {"vendor": self.vendor}
        payload.update(order)
        for key in ("redirect_url", "cancel_url", "webhook"):
            if payload.get(key):
                payload[key] = self.encode_url(payload[key])
        data = self._make_request("POST", "/checkout/create-order", payload)
        return self._handle_response(data)

    def create_minimal_order(self, order):
        """POST /v1/checkout/create-order-minimal — non-card payments only."""
        required = ("order_id", "buyer_email", "buyer_name", "buyer_phone",
                    "amount", "currency")
        missing = [f for f in required if not order.get(f)]
        if missing:
            raise SelcomValidationException(
                "Missing required fields: %s" % ", ".join(missing),
                endpoint="create-order-minimal")
        payload = {"vendor": self.vendor}
        payload.update(order)
        data = self._make_request("POST", "/checkout/create-order-minimal",
                                  payload)
        return self._handle_response(data)

    def cancel_order(self, order_id):
        """DELETE /checkout/cancel-order — refuses terminal statuses first."""
        status = self.get_order_status(order_id)
        items = status.get("data") or []
        current = (items[0].get("payment_status") if items else "") or ""
        if current in ("COMPLETED", "CANCELLED", "USERCANCELLED"):
            raise SelcomOrderException(
                "Cannot cancel order in status %s" % current,
                endpoint="cancel-order")
        return self._make_request("DELETE", "/checkout/cancel-order",
                                  params={"order_id": order_id})

    def get_order_status(self, order_id):
        """GET /checkout/order-status."""
        data = self._make_request("GET", "/checkout/order-status",
                                  params={"order_id": order_id})
        for item in data.get("data") or []:
            item["application_status"] = self.map_payment_status(
                item.get("payment_status"))
        return data

    def list_orders(self, from_date, to_date):
        """GET /checkout/list-orders — validates YYYY-MM-DD and range."""
        for name, value in (("fromdate", from_date), ("todate", to_date)):
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except (TypeError, ValueError):
                raise SelcomValidationException(
                    "%s must be YYYY-MM-DD" % name, endpoint="list-orders")
        if from_date > to_date:
            raise SelcomValidationException(
                "fromdate must be <= todate", endpoint="list-orders")
        return self._make_request("GET", "/checkout/list-orders",
                                  params={"fromdate": from_date,
                                          "todate": to_date})

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------
    def handle_webhook(self, payload):
        """Process a Selcom payment notification (idempotent).

        Returns (selcom.order.record, status_string). Amount/currency are
        verified against the local record before marking paid.
        """
        from .selcom_order import SelcomOrder  # local import to avoid cycle

        order_id = payload.get("order_id") or payload.get("transid")
        if not order_id:
            raise SelcomValidationException("Webhook missing order_id")
        selcom_status = (payload.get("status")
                         or payload.get("payment_status") or "").upper()
        app_status = self.map_payment_status(selcom_status)

        order = self.env["selcom.order"].sudo().search(
            [("order_id", "=", order_id)], limit=1)
        if not order:
            raise SelcomWebhookNotFound(order_id)

        gateway_ref = payload.get("transid") or payload.get("reference")
        # Idempotency: skip if already processed with same gateway ref/status
        if app_status == order.state and \
                gateway_ref and gateway_ref == order.gateway_reference:
            _logger.info("Duplicate Selcom webhook ignored for %s", order_id)
            return order, order.state

        amount = float(payload.get("amount") or 0)
        currency = payload.get("currency") or order.currency_id.name
        if app_status == "paid":
            if amount and order.amount and abs(amount - order.amount) > 0.01:
                _logger.warning(
                    "Selcom AMOUNT MISMATCH for %s: expected %.2f got %.2f "
                    "— NOT marking paid", order_id, order.amount, amount)
                order.write({"state": "pending",
                             "mismatch_flag": True})
                return order, "amount_mismatch"
            if currency != order.currency_id.name:
                _logger.warning(
                    "Selcom CURRENCY MISMATCH for %s: expected %s got %s "
                    "— NOT marking paid", order_id, order.currency_id.name,
                    currency)
                order.write({"state": "pending", "mismatch_flag": True})
                return order, "currency_mismatch"

        order.write({
            "state": app_status,
            "gateway_reference": gateway_ref or order.gateway_reference,
            "channel": payload.get("channel") or order.channel,
            "phone": payload.get("phone") or order.phone,
        })
        _logger.info("Selcom order %s updated to %s", order_id, app_status)
        return order, app_status


class SelcomWebhookNotFound(Exception):
    def __init__(self, order_id):
        super().__init__("Unknown Selcom order: %s" % order_id)
        self.order_id = order_id
