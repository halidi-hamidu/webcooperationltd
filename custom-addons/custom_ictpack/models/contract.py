# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################

from odoo import api, fields, models

class ContractContract(models.Model):

    _inherit = "contract.contract"

    business_line = fields.Selection([
        ('atras', 'IoT VTS'),
        ('ects', 'IoT ECTS'),
        ('itms', 'IT Management & Security Services'),
        ('uis', 'Unified Infrastructure Solutions'),
        ('ictpack', 'Application Software'),
    ], string='Business Line', default='atras',index=True, readonly=False, required=True, copy=False,)

    def _prepare_invoice(self, date_invoice, journal=None):
        vals =  super(ContractContract,self)._prepare_invoice(date_invoice, journal)
        vals.update(
            {
                'business_line': self.business_line
            }
        )
        return vals
    
    
class ContractLine(models.Model):

    _inherit = "contract.line"

    def _insert_markers(self, first_date_invoiced, last_date_invoiced):
        self.ensure_one()
        lang_obj = self.env["res.lang"]
        lang = lang_obj.search([("code", "=", self.contract_id.partner_id.lang)])
        date_format = lang.date_format or "%m/%d/%Y"
        name = self.name
        name = name.replace("#START#", first_date_invoiced.strftime(date_format)  if first_date_invoiced else "#START#")
        name = name.replace("#END#", last_date_invoiced.strftime(date_format) if last_date_invoiced else "#END#")
        return name