# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################
import logging

from odoo import api, fields, models

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
