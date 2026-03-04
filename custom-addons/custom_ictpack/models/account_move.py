# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################
from num2words import num2words

from odoo import api, exceptions, fields, models, _
from odoo.tools import float_is_zero, float_compare, pycompat
from odoo.tools.misc import formatLang

from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    po_no = fields.Char(string='PO Number', default=False, copy=False, help="Purchase Order Number")

    inv_reference = fields.Char(string='Payment Reference', compute='_compute_reference')

    po_date = fields.Datetime('PO Date', copy=False, help="Purchase Order Date")


    business_line = fields.Selection([
        ('atras', 'IoT VTS'),
        ('ects', 'IoT ECTS'),
        ('itms', 'IT Management & Security Services'),
        ('uis', 'Unified Infrastructure Solutions'),
        ('ictpack', 'Application Software'),
    ], string='Business Line',index=True, readonly=False, copy=False,states={'posted': [('readonly', True)],'cancel': [('readonly', True)]})

    amount_in_word = fields.Char(string='Amount in words', readonly=True,default=False, copy=False, compute='_compute_text')

    is_petty = fields.Boolean(string='Is Pettycash voucher', default=False)

    is_payment = fields.Boolean(string='Is Payment voucher',default=False)

    has_duplicate_payment_ref = fields.Boolean(string='Has Duplicate Payment Reference', compute='_compute_has_duplicate_payment_ref', store=False)

    @api.depends('payment_reference')
    def _compute_has_duplicate_payment_ref(self):
        """Check if the payment reference has been used in other invoices."""
        for record in self:
            ref = record.payment_reference
            record_id = record._origin.id
            if ref and isinstance(record_id, int) and record_id:
                domain = [
                    ('payment_reference', '=', ref),
                    ('id', '!=', record_id),
                    ('state', '!=', 'cancel'),
                ]
                existing_invoices = self.env['account.move'].search(domain, limit=1)
                record.has_duplicate_payment_ref = bool(existing_invoices)
            else:
                record.has_duplicate_payment_ref = False

    def action_show_payment_reference_warning(self):
        """Open wizard to show duplicate payment reference warning."""
        self.ensure_one()
        
        # Check if there are duplicates
        if not self.payment_reference:
            return
        
        domain = [
            ('payment_reference', '=', self.payment_reference),
            ('id', '!=', self.id),
            ('state', '!=', 'cancel')
        ]
        existing_invoices = self.env['account.move'].search(domain)
        
        if not existing_invoices:
            return
        
        # Create and open the wizard
        wizard = self.env['payment.reference.warning.wizard'].create({
            'move_id': self.id,
        })
        
        return {
            'name': _('Payment Reference Warning'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.reference.warning.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.model
    def _get_currency_name(self):
        journal = self.env['account.journal'].browse(self._context.get('journal_id', False))
        if journal.currency_id:
            return journal.currency_id.name
        return self.env.user.company_id.currency_id.name
    
    @api.depends('move_type')
    def _compute_invoice_filter_type_domain(self):
        for move in self:
            if move.is_sale_document(include_receipts=True):
                move.invoice_filter_type_domain = 'sale'
            elif move.is_petty:
                move.invoice_filter_type_domain = 'petty'
            elif move.is_payment:
                move.invoice_filter_type_domain = 'payment'
            elif move.is_purchase_document(include_receipts=True):
                move.invoice_filter_type_domain = 'purchase'
            else:
                move.invoice_filter_type_domain = False
    
    def _get_valid_journal_types(self):
        if self.is_sale_document(include_receipts=True):
            return ['sale']
        elif self.is_petty:
            return ['petty']
        elif self.is_payment:
            return ['payment']
        elif self.is_purchase_document(include_receipts=True):
            return ['purchase']
        elif self.payment_ids or self.env.context.get('is_payment'):
            return ['bank', 'cash']
        return ['general']

    @api.depends('name')
    def _compute_reference(self):
        for record in self:
            if record.name:
                invoice_number = record.name.replace("INV", "")
                record.inv_reference = invoice_number.replace("/","")
            else:
                record.inv_reference = record.id

    @api.depends('amount_total')
    def _compute_text(self):
        for record in self:
            currency = ''
            if record.currency_id.name:
                currency = record.currency_id.name
            else:
                currency = record._get_currency_name()
            try:
                record.amount_in_word = num2words(record.amount_total, to='currency', separator=' and', cents=True,
                                                currency=currency, adjective=True).title()
                if currency == 'USD':
                    record.amount_in_word = record.amount_in_word.replace('Us', 'US')

            except NotImplementedError:
                record.amount_in_word = num2words(record.amount_total, to='currency', separator=' and', cents=True).title()
                record.amount_in_word = record.amount_in_word.replace('Euro', 'Tanzanian Shillings')
