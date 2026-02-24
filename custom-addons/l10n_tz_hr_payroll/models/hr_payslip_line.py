# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, _
from odoo.exceptions import UserError


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    def get_payslip_styling_dict(self):
        """Override to apply custom styling for Tanzania payslip lines.

        In Odoo 19, get_payslip_styling_dict returns a dict with keys:
            'line_style', 'line_class', 'o_title'
        Styling is now primarily driven by hr.salary.rule fields:
            bold, italic, underline, space_above, indented, color, title
        """
        result = super().get_payslip_styling_dict()
        # Apply custom teal color for subtotal lines
        subtotal_codes = ('INSURANCE_RELIEF', 'STATUTORY_DED', 'OTHER_DED')
        if self.salary_rule_id.code in subtotal_codes:
            result['line_style'] = 'color:#00A09D;'
            result['line_class'] = result.get('line_class', '') + ' o_subtotal o_border_bottom'
        return result
