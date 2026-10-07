import logging

from odoo import http
from odoo.http import request

from .helpers import (
    authenticate,
    error_response,
    get_pagination_params,
    pagination_meta,
    successful_response,
)

_logger = logging.getLogger(__name__)


class CustomerPortalApiCustomer(http.Controller):

    @http.route("/api/v1/customer/projects", type="http", auth="public",
                csrf=False, methods=["GET"])
    def projects(self, **kwargs):
        user, err = authenticate()
        if err:
            return err
        try:
            page, limit, err = get_pagination_params()
            if err:
                return err
            partner = user.partner_id
            # Runs as the portal user: ir.rules (portal/project security)
            # restrict visibility to their own records automatically.
            domain = [
                "|",
                    ("partner_id", "child_of", partner.ids),
                    ("message_partner_ids", "in", partner.ids),
            ]
            Project = request.env["project.project"]
            total = Project.search_count(domain)
            projects = Project.search(domain, offset=(page - 1) * limit,
                                      limit=limit, order="id desc")
            data = [
                {
                    "id": p.id,
                    "name": p.name,
                    "customer_id": p.partner_id.id or partner.id,
                    "customer_name": p.partner_id.name or partner.name,
                    "description": p.description or "",
                    "active": bool(p.active),
                }
                for p in projects
            ]
            return successful_response(data=data, pagination=pagination_meta(page, limit, total))
        except Exception:
            _logger.exception("Portal API projects error")
            return error_response("INTERNAL_ERROR")

    @http.route("/api/v1/customer/invoices", type="http", auth="public",
                csrf=False, methods=["GET"])
    def invoices(self, **kwargs):
        user, err = authenticate()
        if err:
            return err
        try:
            page, limit, err = get_pagination_params()
            if err:
                return err

            status = (request.params.get("status") or "").strip()
            date_from = request.params.get("date_from")
            date_to = request.params.get("date_to")

            domain = [
                ("move_type", "in", ("out_invoice", "out_refund", "out_receipt")),
            ]
            if status:
                domain.append(("state", "=", status))

            validation_errors = []
            if date_from:
                from .helpers import parse_date
                d = parse_date(date_from, "date_from", validation_errors)
                if d:
                    domain.append(("invoice_date", ">=", d))
            if date_to:
                from .helpers import parse_date
                d = parse_date(date_to, "date_to", validation_errors)
                if d:
                    domain.append(("invoice_date", "<=", d))
            if validation_errors:
                return error_response("VALIDATION_ERROR", "; ".join(validation_errors))

            partner = user.partner_id
            Move = request.env["account.move"]
            # Portal record rules guarantee only the customer's own invoices.
            total = Move.search_count(domain)
            invoices = Move.search(domain, offset=(page - 1) * limit,
                                   limit=limit, order="invoice_date desc, id desc")
            data = [
                {
                    "id": inv.id,
                    "invoice_number": inv.name or "",
                    "customer_id": partner.id,
                    "customer_name": partner.name,
                    "invoice_date": inv.invoice_date and str(inv.invoice_date) or "",
                    "due_date": inv.invoice_date_due and str(inv.invoice_date_due) or "",
                    "currency": inv.currency_id.name or "",
                    "subtotal": inv.amount_untaxed,
                    "tax": inv.amount_tax,
                    "total": inv.amount_total,
                    "amount_due": inv.amount_residual,
                    "amount_paid": inv.amount_total - inv.amount_residual,
                    "status": inv.state,
                    "payment_state": inv.payment_state,
                    "invoice_lines": [
                        {
                            "id": line.id,
                            "product": line.product_id.name or line.name or "",
                            "description": line.name or "",
                            "quantity": line.quantity,
                            "unit_price": line.price_unit,
                            "tax": line.price_tax,
                            "subtotal": line.price_subtotal,
                            "total": line.price_total,
                        }
                        for line in inv.invoice_line_ids
                    ],
                }
                for inv in invoices
            ]
            return successful_response(data=data, pagination=pagination_meta(page, limit, total))
        except Exception:
            _logger.exception("Portal API invoices error")
            return error_response("INTERNAL_ERROR")
