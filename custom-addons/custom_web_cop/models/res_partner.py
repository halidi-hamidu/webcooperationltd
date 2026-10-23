# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    vrn = fields.Char(
        string='VRN',
        help="Taxpayer Identification Number (TIN/VAT Registration Number).")

    till_alias = fields.Char(
        string='Lipa Namba (Till Alias)',
        help="Selcom till alias / payment number used to receive payments "
             "for this partner.")

    outstanding_payment_count = fields.Integer(
        string='Outstanding Payments',
        compute='_compute_outstanding_payment_count')

    def _compute_outstanding_payment_count(self):
        counts = dict(self.env['account.payment']._read_group(
            domain=[
                ('partner_id', 'in', self.ids),
                ('payment_type', '=', 'inbound'),
                ('state', '=', 'in_process'),
                ('is_reconciled', '=', False),
            ],
            groupby=['partner_id'],
            aggregates=['__count'],
        ))
        for partner in self:
            partner.outstanding_payment_count = counts.get(partner, 0)

    def action_view_outstanding_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Outstanding Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.id),
                ('payment_type', '=', 'inbound'),
                ('state', '=', 'in_process'),
                ('is_reconciled', '=', False),
            ],
            'context': {'default_partner_id': self.id},
        }
