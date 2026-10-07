from unittest import mock

from odoo import exceptions, tests

from ..models.exceptions import (
    SelcomApiException,
    SelcomAuthenticationException,
    SelcomOrderException,
    SelcomValidationException,
)
from ..models.selcom_client import Selcom

SUCCESS = {
    "reference": "0289999288",
    "resultcode": "000",
    "result": "SUCCESS",
    "message": "Payment notification logged",
    "data": [{
        "gateway_buyer_uuid": "12344321",
        "payment_token": "80008000",
        "qr": "QR",
        "payment_gateway_url": "aHR0cHM6Ly9leGFtcGxlLmNvbS9wYXk=",
    }],
}


@tests.tagged("post_install", "-at_install")
class TestSelcomUrlBase64(tests.TransactionCase):

    def test_encode_decode_roundtrip(self):
        for url in (
            "https://example.com/payment",
            "http://example.com",
            "https://example.com/pay?x=1&y=2%20space",
            "https://exämple.com/päth",
        ):
            self.assertEqual(Selcom.decode_url(Selcom.encode_url(url)), url)

    def test_empty(self):
        self.assertEqual(Selcom.encode_url(""), "")
        self.assertEqual(Selcom.decode_url(""), "")

    def test_invalid_base64_passthrough(self):
        # Not base64 → assumed to already be a plain URL
        self.assertEqual(Selcom.decode_url("https://plain.url/x"),
                         "https://plain.url/x")


@tests.tagged("post_install", "-at_install")
class TestSelcomStatusMap(tests.TransactionCase):

    def test_mapping(self):
        self.assertEqual(Selcom.map_payment_status("PENDING"), "pending")
        self.assertEqual(Selcom.map_payment_status("INPROGRESS"), "processing")
        self.assertEqual(Selcom.map_payment_status("COMPLETED"), "paid")
        self.assertEqual(Selcom.map_payment_status("CANCELLED"), "cancelled")
        self.assertEqual(Selcom.map_payment_status("USERCANCELLED"), "cancelled")
        self.assertEqual(Selcom.map_payment_status("REJECTED"), "failed")
        self.assertEqual(Selcom.map_payment_status("WHATEVER"), "pending")


@tests.tagged("post_install", "-at_install")
class TestTillAlias(tests.TransactionCase):

    def _partner(self):
        return self.env["res.partner"].create({
            "name": "Selcom Test Customer",
            "email": "selcom.test@example.com",
        })

    def test_creates_till_alias(self):
        p = self._partner()
        p.action_generate_selcom_till_alias()
        self.assertTrue(p.selcom_till_alias.startswith("CUST-%s-" % p.id))

    def test_returns_existing_till_alias(self):
        p = self._partner()
        p.action_generate_selcom_till_alias()
        first = p.selcom_till_alias
        Selcom(self.env).generate_till_alias(p.id, existing=first)
        self.assertEqual(p.selcom_till_alias, first)

    def test_prevents_duplicate_aliases(self):
        p1 = self._partner()
        p1.action_generate_selcom_till_alias()
        p2 = self.env["res.partner"].create({"name": "Second"})
        with self.assertRaises(Exception):
            p2.write({"selcom_till_alias": p1.selcom_till_alias})
            # flush to trigger constraint
            self.env.cr.flush()


@tests.tagged("post_install", "-at_install")
class TestSelcomEndpoints(tests.TransactionCase):

    def _selcom(self):
        return Selcom(self.env)

    def _order_payload(self, **overrides):
        payload = {
            "order_id": "ORD-TEST-001",
            "buyer_email": "john@example.com",
            "buyer_name": "John Joh",
            "buyer_phone": "255712345678",
            "amount": 8000,
            "currency": "TZS",
            "redirect_url": "https://example.com/redirect",
            "cancel_url": "https://example.com/cancel",
            "webhook": "https://example.com/webhook",
        }
        payload.update(overrides)
        return payload

    def test_create_order_success_and_decodes_url(self):
        with mock.patch.object(Selcom, "_make_request",
                               return_value=dict(SUCCESS)):
            result = self._selcom().create_order(self._order_payload())
        self.assertEqual(result["resultcode"], "000")
        url = result["data"][0]["payment_gateway_url"]
        self.assertEqual(url, "https://example.com/pay")

    def test_create_order_validation(self):
        with self.assertRaises(SelcomValidationException):
            self._selcom().create_order({"order_id": "X"})

    def test_minimal_order_success(self):
        payload = self._order_payload()
        for k in ("redirect_url", "cancel_url", "webhook"):
            payload.pop(k)
        with mock.patch.object(Selcom, "_make_request",
                               return_value=dict(SUCCESS)):
            result = self._selcom().create_minimal_order(payload)
        self.assertEqual(result["result"], "SUCCESS")

    def test_cancel_order_blocks_completed(self):
        status = {"data": [{"payment_status": "COMPLETED"}]}
        with mock.patch.object(Selcom, "get_order_status",
                               return_value=status):
            with self.assertRaises(SelcomOrderException):
                self._selcom().cancel_order("ORD-TEST-001")

    def test_cancel_order_success(self):
        status = {"data": [{"payment_status": "PENDING"}]}
        cancelled = dict(SUCCESS, message="Order cancelled successfully",
                         data=[])
        with mock.patch.object(Selcom, "get_order_status",
                               return_value=status):
            with mock.patch.object(Selcom, "_make_request",
                                   return_value=cancelled):
                result = self._selcom().cancel_order("ORD-TEST-001")
        self.assertEqual(result["message"], "Order cancelled successfully")

    def test_order_status_maps_application_status(self):
        status = dict(SUCCESS, data=[{"payment_status": "INPROGRESS"}])
        with mock.patch.object(Selcom, "_make_request", return_value=status):
            result = self._selcom().get_order_status("ORD-TEST-001")
        self.assertEqual(result["data"][0]["application_status"],
                         "processing")

    def test_list_orders_validates_dates(self):
        with self.assertRaises(SelcomValidationException):
            self._selcom().list_orders("2026-13-01", "2026-13-02")
        with self.assertRaises(SelcomValidationException):
            self._selcom().list_orders("2026-10-10", "2026-10-01")

    def test_list_orders_success(self):
        listed = dict(SUCCESS, data=[
            {"order_id": "1", "payment_status": "PENDING"},
            {"order_id": "2", "payment_status": "CANCELLED"},
        ])
        with mock.patch.object(Selcom, "_make_request", return_value=listed):
            result = self._selcom().list_orders("2026-10-01", "2026-10-07")
        self.assertEqual(len(result["data"]), 2)

    def test_api_error_raised(self):
        err = {"resultcode": "417", "result": "ERROR",
               "message": "Duplicate order", "data": []}
        with mock.patch.object(Selcom, "_make_request",
                               side_effect=SelcomApiException(
                                   "Duplicate order", result_code="417")):
            with self.assertRaises(SelcomApiException):
                self._selcom().create_order(self._order_payload())

    def test_auth_error_raised(self):
        with mock.patch.object(Selcom, "_make_request",
                               side_effect=SelcomAuthenticationException(
                                   "auth failed")):
            with self.assertRaises(SelcomAuthenticationException):
                self._selcom().create_order(self._order_payload())


@tests.tagged("post_install", "-at_install")
class TestSelcomWebhook(tests.TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({
            "name": "Webhook Customer", "email": "wh@example.com"})
        self.order = self.env["selcom.order"].create({
            "order_id": "ORD-WH-001",
            "partner_id": self.partner.id,
            "amount": 10_000.0,
        })

    def _notify(self, **payload):
        base = {"order_id": "ORD-WH-001", "transid": "T1",
                "amount": 10_000, "currency": "TZS"}
        base.update(payload)
        return base

    def test_valid_webhook_marks_paid(self):
        order, status = Selcom(self.env).handle_webhook(
            self._notify(status="COMPLETED"))
        self.assertEqual(status, "paid")
        self.assertEqual(order.state, "paid")

    def test_duplicate_webhook_is_idempotent(self):
        s = Selcom(self.env)
        s.handle_webhook(self._notify(status="COMPLETED"))
        order, status = s.handle_webhook(self._notify(status="COMPLETED"))
        self.assertEqual(status, "paid")

    def test_rejected_payment(self):
        order, status = Selcom(self.env).handle_webhook(
            self._notify(status="REJECTED"))
        self.assertEqual(status, "failed")

    def test_amount_mismatch_not_paid(self):
        order, status = Selcom(self.env).handle_webhook(
            self._notify(status="COMPLETED", amount=5_000))
        self.assertEqual(status, "amount_mismatch")
        self.assertNotEqual(order.state, "paid")
        self.assertTrue(order.mismatch_flag)

    def test_currency_mismatch_not_paid(self):
        order, status = Selcom(self.env).handle_webhook(
            self._notify(status="COMPLETED", currency="USD"))
        self.assertEqual(status, "currency_mismatch")
        self.assertNotEqual(order.state, "paid")

    def test_unknown_order(self):
        from ..models.selcom_client import SelcomWebhookNotFound
        with self.assertRaises(SelcomWebhookNotFound):
            Selcom(self.env).handle_webhook(
                {"order_id": "NOPE", "status": "COMPLETED"})

    def test_missing_order_id(self):
        with self.assertRaises(SelcomValidationException):
            Selcom(self.env).handle_webhook({"status": "COMPLETED"})
