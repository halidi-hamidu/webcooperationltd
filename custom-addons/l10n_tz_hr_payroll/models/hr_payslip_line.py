# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, _
from odoo.exceptions import UserError


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    def get_payslip_styling_dict(self):
        result = super().get_payslip_styling_dict()
        result.update({
            'INSURANCE_RELIEF': {
                'line_style': 'color:#00A09D;',
                'line_class': 'o_subtotal o_border_bottom',
            },
            'STATUTORY_DED': {
                'line_style': 'color:#00A09D;',
                'line_class': 'o_subtotal o_border_bottom',
            },
            'OTHER_DED': {
                'line_style': 'color:#00A09D;',
                'line_class': 'o_subtotal o_border_bottom',
            },
        })
        return result
