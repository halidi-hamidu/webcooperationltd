# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import frozendict


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    # == Business fields ==
    business_line = fields.Selection([
        ('atras', 'IoT VTS'),
        ('ects', 'IoT ECTS'),
        ('itms', 'IT Management & Security Services'),
        ('uis', 'Unified Infrastructure Solutions'),
        ('ictpack', 'Application Software'),
    ], string='Business Line',)
    
  
    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super(AccountPaymentRegister, self)._create_payment_vals_from_wizard(batch_result)
        payment_vals['business_line'] = self.business_line
        return payment_vals