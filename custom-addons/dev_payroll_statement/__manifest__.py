##############################################################################
#    
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Devintelle Solutions (<http://devintellecs.com/>).
#
##############################################################################

{
    'name': 'Employee Payroll Statement',
    'version': "16.0.1.0.0",
    'category': 'Generic Modules/Human Resources',
    'sequence':1,
    'summary': 'App will print employee payroll monthly statement with salary rules',
    'description': """
        App will print employee payroll monthly statement with salary rules

Employee payslip statement, payroll statement, hr payslip statement, hr payroll , hr employee payroll, payroll summary report, emploee payslip by monthly, payslip ragistar, employee payslip generator, payslip salary rule , employee salary rule
Employee payroll statement
HR payroll
HR employee payroll
HR employee payroll statement
Print payroll statement
Print employee payroll statement
Print detailed employee payroll statement
Payroll monthly statement
Export payroll statement
Export employee payroll
Export employee payroll statement
Monthly payroll statement
Monthly employee payroll statement
Payroll report
HR payroll report
Payroll report for HR
Payroll statement odoo
HR payroll statement odoo
Employee payroll statement odoo
Payroll summary report
payroll summary by salary rule
payroll salary rule statement
employee payroll statement
odoo payroll summary 
export payroll summary in odoo
payroll department wise statement
payroll department wise statement in odoo
payroll job wise statement
payroll job wise statement in odoo
monthly payroll statement 
odoo monthly payroll statement 

            """,
    'author': 'DevIntelle Consulting Service Pvt.Ltd',
    'website': 'http://www.devintellecs.com/',
    'depends': ['hr_payroll'],
    'data': [
        'wizard/emp_payroll_statement_view.xml',
        'views/payroll_statement_tempate.xml',
        'views/payroll_statement_report_menu.xml',        
    ],
    'demo': [],
    'test': [],
    'css': [],
    'qweb': [],
    'js': [],
    'images': ['images/main_screenshot.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'price':39.0,
    'currency':'EUR',
    'live_test_url':'https://youtu.be/TpBgCFsyOsc',
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
