# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################

from odoo import api, exceptions, fields, models, _
# pycompat has been removed in modern Odoo versions, so it is best to remove it from imports
from odoo.tools import float_is_zero, float_compare
from odoo.tools.misc import formatLang
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError

# Rename the class to reflect the new model (optional but recommended)
class HrVersion(models.Model):
    # In Odoo 19, 'hr.contract' is replaced by 'hr.version'
    _inherit = 'hr.version'

    x_heslb = fields.Boolean(string='Is a HESLB Beneficiary', default=False, copy=False, help="Tick the Box if this employee is a beneficiary of Students' Loans Board, otherwise leave empty.")
    x_director = fields.Boolean(string='Is a Company Director', default=False, copy=False, help="Is he/she a company director?")

    # Monetary fields work identically, as 'hr.version' handles the base wages and carries the currency_id natively
    x_heslb_manual = fields.Monetary(string='HESLB Manual Adjustment', copy=False, help="Input manual amount if the regular HESLB 15% deduction does not apply. Remember to UNCHECK the 'Is HESLB Beneficiary' before using this field!")
    x_manual_deductions = fields.Monetary(string='Other Manual Deductions', help="Other manual deductions by the company to the employee")
    x_sacco_loan = fields.Monetary(string='SACCO Loan Repayment', help="SACCO Loan Repayment to be deducted from NetPay")
    x_savings = fields.Monetary(string='SACCOS Savings', help="Amount to be deducted from NetPay for SACCO savings")

    x_security_calculation = fields.Boolean(string='Social Security Applicable', help="Tick Yes if Calculation of Social Security is Applicable")
    x_topup = fields.Monetary(string='Salary Topup', help="Employee Topup")
    hra = fields.Monetary(string='Allowances', help="Allowances")
    x_unpaid_leave = fields.Monetary(string='Unpaid Leaves/Absent', help="Amount of money accrued as a result of unpaid leaves")