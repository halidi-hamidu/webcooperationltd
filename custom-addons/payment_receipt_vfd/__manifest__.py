# -*- coding: utf-8 -*-
{
    'name': "PAYMENT RECEIPT VFD",
    'summary': "Payment Receipt VFD",
    'description': "Payment Receipt VFD",
    'author': "WebCoop Solutions LTD",
    'website': "http://www.webcooperationltd.com",
    'category': 'Services',
    'version': '0.1',
    'depends': ['base', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_views.xml',
        'views/vfd_paperformat.xml',
        'views/receipt_template.xml',
        'views/vfd_configurations.xml',
        'views/account_move.xml',
        'views/payment_receipt_vfd.xml',
        'views/payment_receipt_res.xml',
    ],
    'installable': True,
}
