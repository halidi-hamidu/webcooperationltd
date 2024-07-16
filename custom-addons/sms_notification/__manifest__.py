# -*- coding: utf-8 -*-
{
    'name': "SMS NOTIFICATIONS",

    'summary': """
        This module sends SMS notifications/reminders for recurring invoices""",

    'description': """
        This module sends SMS notifications for recurring invoices 
        - It sends 15 days before next invoice date reminder to clients for monthly service payments.
        - Sends the sms reminder on the last day of the last month of the service.
        - Sends another reminder 7 days after the last month of the service.
        - Sends sms reminders for overdue invoices to customers.
            """,

    'author': "IctPack Solutions LTD",
    'website': "https://www.ictpack.com",
    'category': 'Sales',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['sms','account','sale','custom_ictpack'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/sms_views.xml',
        'views/sms_configuration_views.xml',
        'views/sale_order_views.xml',
        'views/account_move.xml',
        'data/sms_templates.xml',
        'data/ir_cron_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [],
    'auto_install': False,
    'installable': True,
    'application': True,
}
