# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Tanzania - Payroll',
    'category': 'Human Resources/Payroll',
    'depends': ['hr_payroll','custom_ictpack', 'hr_work_entry_holidays', 'hr_payroll_holidays'],
    'version': '1.0',
    'description': """
    Tanzania Payroll Rules.
=====================

    * Employee Details
    * Employee Contracts
    * Allowances/Deductions
    * Allow to configure Basic/Gross/Net Salary
    * Employee Payslip
    * Integrated with Leaves Management
    """,
    'data': [
        'data/hr_salary_rule_category_data.xml',
        'data/hr_payroll_structure_type_data.xml',
        'data/hr_payroll_structure_data.xml',
        'data/hr_payslip_input_type_data.xml',
        'data/hr_rule_parameters_data.xml',
        'data/hr_salary_rule_data.xml',
        # 'views/hr_contract_views.xml',
        'views/report_payslip_templates.xml',
    ],
    'license': 'OEEL-1',
}
