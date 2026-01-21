# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    sms_count = fields.Integer("SMS", compute='_compute_sms_count')

    def _compute_sms_count(self):
        """Compute SMS count from mailing.mailing records targeting this partner"""
        for partner in self:
            # Count mailings where this partner is in the mailing_domain
            mailing_count = self.env['mailing.mailing'].search_count([
                ('mailing_type', '=', 'sms'),
                ('mailing_domain', 'ilike', f"('id', '=', {partner.id})")
            ])
            partner.sms_count = mailing_count

    def action_open_sms_notification(self):
        """Open mailing.mailing view filtered for this partner's SMS mailings"""
        action = self.env["ir.actions.actions"]._for_xml_id("mass_mailing_sms.mailing_mailing_action_sms")
        action['context'] = {'default_mailing_type': 'sms'}
        
        # Filter mailings targeting this partner
        action['domain'] = [
            ('mailing_type', '=', 'sms'),
            ('mailing_domain', 'ilike', f"('id', '=', {self.id})")
        ]
        
        return action
