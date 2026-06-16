# -*- coding: utf-8 -*-
import base64
from odoo import models
from .utils import format_response

class AccountMove(models.Model):
    _inherit = 'account.move'

    # def search_invoice_by_number(self, invoice_id):
    #     """
    #     Search for a customer invoice by its invoice number (name).
    #     Returns basic invoice details for display on mobile before download.
    #     """
    #     invoice = self.sudo().browse(invoice_id).exists()

    #     if not invoice:
    #         return format_response('error', 'Invoice not found.', [])

    #     return format_response('success', 'Invoice found.', {
    #         'id': invoice.id,
    #         'invoice_number': invoice.name,
    #         'date': str(invoice.invoice_date) if invoice.invoice_date else '',
    #         'due_date': str(invoice.invoice_date_due) if invoice.invoice_date_due else '',
    #         'customer_id': invoice.partner_id.id,
    #         'customer_name': invoice.partner_id.name,
    #         'amount_total': invoice.amount_total,
    #         'amount_residual': invoice.amount_residual,
    #         'currency': invoice.currency_id.name,
    #         'state': invoice.state,
    #         'payment_state': invoice.payment_state,
    #     })

    def download_invoice_pdf(self, invoice_id):
        """
        Generate and return a customer invoice PDF as a base64-encoded string.
        The mobile client can decode this and present it as a downloadable PDF.
        """
        invoice = self.sudo().browse(invoice_id).exists()

        if not invoice:
            return format_response('error', 'Invoice not found.', [])

        try:
            pdf_content, _ = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                'account.account_invoices', [invoice.id]
            )
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')

            invoice_name = invoice.name or str(invoice.id)
            return format_response('success', 'Invoice PDF generated successfully.', {
                'invoice_number': invoice_name,
                'customer_name': invoice.partner_id.name,
                'filename': f'Invoice_{invoice_name.replace("/", "-")}.pdf',
                'pdf_base64': pdf_base64,
                'mime_type': 'application/pdf',
            })
        except Exception as e:
            return format_response('error', f'Failed to generate PDF: {str(e)}', [])
