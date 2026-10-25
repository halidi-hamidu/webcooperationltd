# -*- coding: utf-8 -*-
{
    'name': "Tanzania HR Payroll",
    'summary': "Tanzania localized HR Payroll",
    'author': "WebCoop Solutions LTD",
    'website': "https://www.webcooperationltd.com",
    'category': 'Human Resources/Payroll',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['hr_payroll', 'hr_contract_types'],
    'data': [
        'data/hr_salary_rule_category_data.xml',
        'data/hr_salary_rule_data.xml',
        'data/hr_rule_parameters_data.xml',
        'data/hr_payroll_structure_data.xml',
        'data/hr_payroll_structure_type_data.xml',
        'data/hr_payslip_input_type_data.xml',
    ],
    'installable': True,
}
