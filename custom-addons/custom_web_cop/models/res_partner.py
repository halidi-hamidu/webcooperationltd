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

    till_alias_synced = fields.Boolean(
        string='Till Alias Synced',
        default=False,
        help="Whether the till alias has been registered/synced with the "
             "Selcom gateway.")

    outstanding_payment_count = fields.Integer(
        string='Outstanding Payments',
        compute='_compute_outstanding_payment_count')

    def _compute_outstanding_payment_count(self):
        payment_data = self.env['account.payment'].read_group(
            domain=[
                ('partner_id', 'in', self.ids),
                ('payment_type', '=', 'inbound'),
                ('state', '=', 'in_process'),
                ('is_reconciled', '=', False),
            ],
            fields=['partner_id'],
            groupby=['partner_id'],
        )
        counts = {row['partner_id'][0]: row['partner_id_count']
                  for row in payment_data}
        for partner in self:
            partner.outstanding_payment_count = counts.get(partner.id, 0)

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

    def action_create_till_alias(self):
        """Create/register a till alias for the partner.

        Placeholder implementation: generates a deterministic alias from the
        partner and marks it synced. Replace with the actual Selcom API call
        when the gateway integration is wired up.
        """
        for partner in self:
            if not partner.till_alias:
                base = (partner.name or 'customer').lower().replace(' ', '')
                partner.till_alias = "till_%s_%s" % (partner.id, base[:12])
            partner.till_alias_synced = True
            partner.message_post(
                body="Till alias created/synced: %s" % partner.till_alias)
        return True
