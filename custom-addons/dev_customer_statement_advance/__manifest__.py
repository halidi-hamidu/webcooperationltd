# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle 
#
##############################################################################

{
    'name': 'Customer Account Statement Advance',
    'version': '16.0.1.0',
    'category': 'Accounting',
    'description': """
         odoo Module will print customer statement with Monthly aging 
         
         partner Aging,
         customer Aging,
         odoo partner Aging
         odoo customer Aging,
         odoo partner statement ,
         odoo customer statement,
         odoo customer statement by invoice date,
         odoo customer statement by due date,
         customer statement by due date,
         customer statement by invoice date,
         partner statement by due date,
         partner statement by invoice date,
         outstanding statement,
         Customer outstanding statement,
         Odoo Customer outstanding statement,
         odoo customer overdue payment,
         Customer overdue payment, 
         Odoo overdue payment, 
         Odoo overdue statement,
         
         Odoo app Print Customer Statement with invoice date/due date and partner aging, customer statement, partner statement, partner aging, supplier statement, vendor statement, payment reminder, customer followup, report, send a statement

    """,
    'summary':'Odoo app Print Customer Statement with invoice date/due date and partner aging, customer statement, partner statement, partner aging, supplier statement, vendor statement, payment reminder, customer followup, report, send a statement',
    'depends': ['sale_management','mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_view.xml',
        'wizard/customer_statement_views.xml',
        'wizard/due_partner_views.xml',
        'report/header.xml',
        'report/customer_statement_template.xml',
        'report/report_menu.xml',
        'edi/mail_template.xml',
        
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
    
    #author and support Details
    'author': 'DevIntelle Consulting Service Pvt.Ltd',
    'website': 'https://www.devintellecs.com',    
    'maintainer': 'DevIntelle Consulting Service Pvt.Ltd', 
    'support': 'devintelle@gmail.com',
    'price':111.0,
    'currency':'EUR',
    #'live_test_url':'https://youtu.be/A5kEBboAh_k',
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
