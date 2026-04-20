from odoo import models, fields, api, _
import hmac
import hashlib
import logging
from decimal import Decimal

_logger = logging.getLogger(__name__)


class CipsWebhookHandler(models.AbstractModel):
    _name = 'cips.webhook.handler'
    _description = 'CIPS Webhook Handler'

    def verify_hmac(self, body, signature, timestamp, secret):
        """
        Verify HMAC-SHA256 signature from CIPS.
        CIPS signs: HMAC-SHA256(secret, "{timestamp}.{payload}")
        and sends the result as "sha256=<hex>" in X-CIPS-Signature.
        The secret is used as plain UTF-8 bytes.
        """
        if not signature or not secret:
            _logger.warning("CIPS HMAC check: missing signature=%s or secret configured=%s",
                            bool(signature), bool(secret))
            return False

        if not timestamp:
            _logger.warning("CIPS HMAC check: missing X-CIPS-Timestamp header")
            return False

        payload_str = body.decode() if isinstance(body, bytes) else body
        message = "{}.{}".format(timestamp, payload_str)

        # Secret is plain UTF-8 (as per CIPS: secret.encode())
        expected_hex = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        # CIPS sends "sha256=<hex>" — strip the prefix
        normalized = signature.lower()
        if normalized.startswith("sha256="):
            normalized = normalized[len("sha256="):]

        if hmac.compare_digest(expected_hex, normalized):
            return True

        _logger.warning(
            "CIPS HMAC mismatch — expected=%s...  received=%s...",
            expected_hex[:16],
            normalized[:16],
        )
        return False

    def handle_till_alias_payment(self, data):
        """
        Process a till_alias.payment_received webhook event.
        Finds the customer by customer_id (Odoo partner.id as string)
        and creates a posted inbound payment. Reconciliation is left to
        the accountant.
        """
        customer_id = data.get("customer_id")
        amount_paid = Decimal(str(data.get("amount", "0")))
        gateway_ref = data.get("gateway_reference")
        channel = data.get("channel", "")
        payer_phone = data.get("payer_phone", "")

        # Build memo upfront so the idempotency check uses the exact same value
        memo = "Selcom {} — {} / {}".format(channel, payer_phone, gateway_ref)

        # --- Guard: idempotency — reject duplicate callbacks using the dedicated gateway ref field ---
        existing = self.env["account.payment"].search(
            [("cips_gateway_ref", "=", gateway_ref)], limit=1
        )
        if existing:
            _logger.warning("Duplicate CIPS callback ignored: %s", gateway_ref)
            return

        # --- Find the customer by Odoo partner ID ---
        try:
            partner_id_int = int(customer_id)
        except (TypeError, ValueError):
            _logger.error(
                "CIPS webhook: invalid customer_id=%s for ref=%s",
                customer_id, gateway_ref,
            )
            self._log_unmatched_callback(data, reason="invalid customer_id format")
            return

        partner = self.env["res.partner"].search(
            [("id", "=", partner_id_int)], limit=1
        )
        if not partner:
            _logger.error(
                "CIPS webhook: no customer found for customer_id=%s ref=%s",
                customer_id, gateway_ref,
            )
            self._log_unmatched_callback(data, reason="customer not found")
            return

        # --- Create and post the inbound payment ---
        tzs_currency = self.env.ref("base.TZS", raise_if_not_found=False)
        cips_journal = self._get_cips_journal()

        payment = self.env["account.payment"].sudo().create({
            "company_id": cips_journal.company_id.id,
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner.id,
            "amount": float(amount_paid),
            "currency_id": tzs_currency.id if tzs_currency else self.env.company.currency_id.id,
            "journal_id": cips_journal.id,
            "memo": memo,
            "cips_gateway_ref": gateway_ref,
            "date": fields.Date.today(),
        })
        payment.action_post()

        _logger.info(
            "CIPS webhook: payment %s posted for partner=%s amount=%s TZS — awaiting manual reconciliation.",
            gateway_ref, partner.id, amount_paid,
        )
        self._log_payment_event(partner, gateway_ref, amount_paid, data)

    def _get_cips_journal(self):
        """Return the journal flagged for CIPS/Selcom payments."""
        journal = self.env["account.journal"].search(
            [("is_cips_journal", "=", True)], limit=1
        )
        if not journal:
            raise ValueError(
                "No journal is configured for CIPS/Selcom payments. "
                "Please enable 'Used for CIPS / Selcom Payments' on a journal "
                "under Accounting > Configuration > Journals."
            )
        return journal

    def _log_unmatched_callback(self, data, reason=""):
        """Log unmatched callbacks as a note on the company record."""
        company = self.env.company
        message = (
            "<b>Unmatched CIPS callback</b><br/>"
            "Reason: {reason}<br/>"
            "Gateway Ref: {ref}<br/>"
            "Customer ID: {cid}<br/>"
            "Amount: {amount} {currency}<br/>"
            "Channel: {channel}"
        ).format(
            reason=reason,
            ref=data.get("gateway_reference", "—"),
            cid=data.get("customer_id", "—"),
            amount=data.get("amount", "—"),
            currency=data.get("currency", "TZS"),
            channel=data.get("channel", "—"),
        )
        company.message_post(body=message, subject="Unmatched CIPS Payment", body_is_html=True)

    def _log_payment_event(self, partner, gateway_ref, amount, data):
        """Post a chatter note on the partner after successful processing."""
        channel = data.get("channel", "")
        payer_phone = data.get("payer_phone", "")
        message = (
            "<b>CIPS Payment Received</b><br/>"
            "Gateway Ref: {ref}<br/>"
            "Amount: {amount} TZS<br/>"
            "Channel: {channel} — {phone}<br/>"
            "Status: Payment posted. Awaiting manual reconciliation by accountant."
        ).format(
            ref=gateway_ref,
            amount=amount,
            channel=channel,
            phone=payer_phone,
        )
        partner.message_post(body=message, subject="Selcom Payment Processed", body_is_html=True)
