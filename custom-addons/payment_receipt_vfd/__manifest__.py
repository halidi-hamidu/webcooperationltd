# -*- coding: utf-8 -*-
{
    'name': "PAYMENT RECEIPT VFD",

    'summary': """
        Payment Receipt VFD""",

    'description': """
        Payment Receipt VFD
    """,

    'author': "IctPack Solutions LTD",
    'website': "http://www.ictpack.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Services',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account','custom_ictpack'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_views.xml',
        'views/receipt_template.xml',
        'views/vfd_configurations.xml',
        'views/account_move.xml',
        'views/payment_receipt_vfd.xml',
        'views/payment_receipt_res.xml'
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
