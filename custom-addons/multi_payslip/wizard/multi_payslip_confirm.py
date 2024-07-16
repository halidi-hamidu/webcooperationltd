
from odoo import models, api


class MultiPaySlipWiz(models.TransientModel):
    _name = 'multi.payslip.wizard'
    _description = 'Multi Pay Slip Wiz'

    def multi_payslip(self):
        payslip_ids = self.env['hr.payslip']. \
            browse(self._context.get('active_ids'))
        for payslip in payslip_ids:
            if payslip.state in ['verify', 'draft']:
            	#payslip.compute_sheet()
            	payslip.action_payslip_done()
