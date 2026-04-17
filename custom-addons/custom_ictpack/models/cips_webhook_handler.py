from odoo import models, fields, api, _
import hmac
import hashlib
import logging
from decimal import Decimal

_logger = logging.getLogger(__name__)


class CipsWebhookHandler(models.AbstractModel):
    _name = 'cips.webhook.handler'
    _description = 'CIPS Webhook Handler'

    def verify_hmac(self, body, signature, secret):
        """
        Verify HMAC-SHA256 signature from CIPS.
        CIPS signs with: HMAC-SHA256(secret, body)
        Header: X-CIPS-Signature
        """
        if not signature or not secret:
            return False
        expected = hmac.new(
            secret.encode(),
            body if isinstance(body, bytes) else body.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def handle_till_alias_payment(self, data):
        """
        Process a till_alias.payment_received webhook event.
        Finds the customer by customer_id (Odoo partner.id as string),
        creates an inbound payment, and reconciles open invoices FIFO.
        """
        customer_id = data.get("customer_id")
        amount_paid = Decimal(str(data.get("amount", "0")))
        gateway_ref = data.get("gateway_reference")
        channel = data.get("channel", "")
        payer_phone = data.get("payer_phone", "")

        # --- Guard: idempotency — reject duplicate callbacks ---
        existing = self.env["account.payment"].search(
            [("ref", "=", gateway_ref)], limit=1
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
            [("id", "=", partner_id_int), ("customer_rank", ">", 0)], limit=1
        )
        if not partner:
            _logger.error(
                "CIPS webhook: no customer found for customer_id=%s ref=%s",
                customer_id, gateway_ref,
            )
            self._log_unmatched_callback(data, reason="customer not found")
            return

        # --- Fetch open invoices FIFO (oldest due date first) ---
        open_invoices = self.env["account.move"].search(
            [
                ("partner_id", "=", partner.id),
                ("move_type", "=", "out_invoice"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("state", "=", "posted"),
            ],
            order="invoice_date_due asc, date asc",
        )

        if not open_invoices:
            _logger.warning(
                "CIPS webhook: payment %s for customer_id=%s but no open invoices. "
                "Amount=%s TZS — posting as unallocated credit.",
                gateway_ref, customer_id, amount_paid,
            )
            self._post_as_unallocated_credit(partner, amount_paid, gateway_ref, data)
            return

        # --- Register inbound payment ---
        tzs_currency = self.env.ref("base.TZS", raise_if_not_found=False)
        selcom_journal = self._get_selcom_journal()

        payment = self.env["account.payment"].create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner.id,
            "amount": float(amount_paid),
            "currency_id": tzs_currency.id if tzs_currency else self.env.company.currency_id.id,
            "journal_id": selcom_journal.id,
            "ref": gateway_ref,
            "memo": "Selcom {} — {}".format(channel, payer_phone),
            "date": fields.Date.today(),
        })
        payment.action_post()

        # --- Apply to invoices FIFO ---
        remaining = amount_paid

        for invoice in open_invoices:
            if remaining <= 0:
                break

            invoice_due = Decimal(str(invoice.amount_residual))

            if remaining >= invoice_due:
                lines = (payment.line_ids | invoice.line_ids).filtered(
                    lambda l: l.account_id.account_type in (
                        'asset_receivable', 'liability_payable'
                    ) and not l.reconciled
                )
                if lines:
                    lines.reconcile()
                remaining -= invoice_due
            else:
                self._partial_reconcile(payment, invoice)
                remaining = Decimal("0")

        if remaining > 0:
            _logger.info(
                "CIPS webhook: overpayment of %s TZS for customer_id=%s ref=%s. "
                "Remaining credit stays on account.",
                remaining, customer_id, gateway_ref,
            )

        self._log_payment_event(partner, gateway_ref, amount_paid, remaining, data)

    def _post_as_unallocated_credit(self, partner, amount, gateway_ref, raw_data):
        """Post an advance payment when no open invoices exist."""
        tzs_currency = self.env.ref("base.TZS", raise_if_not_found=False)
        selcom_journal = self._get_selcom_journal()
        channel = raw_data.get("channel", "")
        payer_phone = raw_data.get("payer_phone", "")

        payment = self.env["account.payment"].create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner.id,
            "amount": float(amount),
            "currency_id": tzs_currency.id if tzs_currency else self.env.company.currency_id.id,
            "journal_id": selcom_journal.id,
            "ref": gateway_ref,
            "memo": "Selcom {} — {} (unallocated)".format(channel, payer_phone),
            "date": fields.Date.today(),
        })
        payment.action_post()
        _logger.info(
            "CIPS webhook: unallocated credit payment posted for partner=%s ref=%s",
            partner.id, gateway_ref,
        )

    def _partial_reconcile(self, payment, invoice):
        """Reconcile payment against invoice using available credit lines."""
        lines = (payment.line_ids | invoice.line_ids).filtered(
            lambda l: l.account_id.account_type in (
                'asset_receivable', 'liability_payable'
            ) and not l.reconciled
        )
        if lines:
            lines.reconcile()

    def _get_selcom_journal(self):
        """Return the dedicated Selcom journal (code=SELCOM, type=bank)."""
        journal = self.env["account.journal"].search(
            [("code", "=", "SELCOM"), ("type", "=", "bank")], limit=1
        )
        if not journal:
            raise ValueError(
                "No journal with code 'SELCOM' and type 'bank' found. "
                "Please create it under Accounting > Journals."
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

    def _log_payment_event(self, partner, gateway_ref, amount, remaining, data):
        """Post a chatter note on the partner after successful processing."""
        channel = data.get("channel", "")
        payer_phone = data.get("payer_phone", "")
        message = (
            "<b>CIPS Payment Received</b><br/>"
            "Gateway Ref: {ref}<br/>"
            "Amount: {amount} TZS<br/>"
            "Channel: {channel} — {phone}<br/>"
            "Unreconciled remainder: {remaining} TZS"
        ).format(
            ref=gateway_ref,
            amount=amount,
            channel=channel,
            phone=payer_phone,
            remaining=remaining,
        )
        partner.message_post(body=message, subject="Selcom Payment Processed", body_is_html=True)
