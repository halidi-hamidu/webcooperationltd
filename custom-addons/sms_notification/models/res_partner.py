# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    #project_ids = fields.One2many('project.project', 'customer_project_id')
    sms_count = fields.Integer("SMS", compute='_compute_sms_count')

    def _compute_sms_count(self):
        # retrieve all children partners and prefetch 'parent_id' on them
        all_partners = self.with_context(active_test=False).search([('id', 'child_of', self.ids)])
        all_partners.read(['parent_id'])

        # group sms by partner, and account for each partner in self
        groups = self.env['sms.notification'].read_group(
            [('customer', 'in', all_partners.ids)],
            fields=['customer'], groupby=['customer'],
        )
        self.sms_count = 0
        for group in groups:
            partner = self.browse(group['customer'][0])
            while partner:
                if partner in self:
                    partner.sms_count += group['customer_count']
                partner = partner.parent_id

    def action_open_sms_notification(self):
        action = self.env["ir.actions.actions"]._for_xml_id("sms_notification.sms_act_window")
        action['context'] = {}
        all_child = self.with_context(active_test=False).search([('id', 'child_of', self.ids)])
        action['domain'] = ['|', ('customer', 'in', self.ids), ('customer', 'in', all_child.ids)]
        return action
