# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################

from odoo import api, fields, models, _
from markupsafe import Markup


class PaymentReferenceWarningWizard(models.TransientModel):
    _name = 'payment.reference.warning.wizard'
    _description = 'Payment Reference Warning Wizard'

    move_id = fields.Many2one('account.move', string='Invoice', required=True)
    payment_reference = fields.Char(string='Payment Reference', related='move_id.payment_reference', readonly=True)
    warning_message = fields.Html(string='Warning Message', compute='_compute_warning_message')
    duplicate_invoice_ids = fields.Many2many('account.move', string='Duplicate Invoices', compute='_compute_duplicate_invoices')

    @api.depends('move_id', 'payment_reference')
    def _compute_duplicate_invoices(self):
        """Find all invoices with the same payment reference."""
        for wizard in self:
            if wizard.payment_reference and wizard.move_id:
                domain = [
                    ('payment_reference', '=', wizard.payment_reference),
                    ('id', '!=', wizard.move_id.id),
                    ('state', '!=', 'cancel')
                ]
                wizard.duplicate_invoice_ids = self.env['account.move'].search(domain)
            else:
                wizard.duplicate_invoice_ids = False

    @api.depends('duplicate_invoice_ids', 'payment_reference')
    def _compute_warning_message(self):
        """Build the warning message with clickable invoice links."""
        for wizard in self:
            if wizard.duplicate_invoice_ids:
                invoice_links = []
                
                for invoice in wizard.duplicate_invoice_ids:
                    invoice_name = invoice.name or 'Draft'
                    partner_name = invoice.partner_id.name or 'Unknown Partner'
                    invoice_date = invoice.invoice_date.strftime('%Y-%m-%d') if invoice.invoice_date else 'N/A'
                    amount = f"{invoice.currency_id.symbol}{invoice.amount_total:,.2f}" if invoice.currency_id else f"{invoice.amount_total:,.2f}"
                    
                    invoice_links.append(
                        f'<tr>'
                        f'<td style="padding: 8px; border: 1px solid #dee2e6;"><strong>{invoice_name}</strong></td>'
                        f'<td style="padding: 8px; border: 1px solid #dee2e6;">{partner_name}</td>'
                        f'<td style="padding: 8px; border: 1px solid #dee2e6;">{invoice_date}</td>'
                        f'<td style="padding: 8px; border: 1px solid #dee2e6; text-align: right;">{amount}</td>'
                        f'<td style="padding: 8px; border: 1px solid #dee2e6;">{invoice.state.replace("_", " ").title()}</td>'
                        f'</tr>'
                    )
                
                invoice_table = ''.join(invoice_links)
                warning_message = Markup(
                    f'<div style="padding: 15px;">'
                    f'<div style="margin-bottom: 15px; padding: 12px; border-left: 4px solid #ffc107; border-radius: 4px; width: 50em;">'
                    f'<p style="margin: 0; font-size: 14px;"><strong><i class="fa fa-exclamation-triangle"></i> Warning:</strong> '
                    f'The payment reference <strong>"{wizard.payment_reference}"</strong> has already been used in <strong>{len(wizard.duplicate_invoice_ids)}</strong> other invoice(s).</p>'
                    f'</div>'
                    f'<p style="margin-bottom: 10px; font-size: 13px;">The following invoices are using this payment reference:</p>'
                    f'<p style="margin: 10px 0 0 0; font-size: 12px; color: #6c757d;"><em><i class="fa fa-info-circle"></i> '
                    f'Please verify if this is the correct payment reference. You can click on the invoices below to view their details.</em></p>'
                    f'</div>'
                )
                wizard.warning_message = warning_message
            else:
                wizard.warning_message = False

    def action_view_invoice(self):
        """Open the selected invoice in form view."""
        self.ensure_one()
        invoice_id = self.env.context.get('invoice_id')
        if invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': invoice_id,
                'view_mode': 'form',
                'target': 'new',
            }

    def action_continue(self):
        """Close the wizard and allow the user to continue."""
        return {'type': 'ir.actions.act_window_close'}
