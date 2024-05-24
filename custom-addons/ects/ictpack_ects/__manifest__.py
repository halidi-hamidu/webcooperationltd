# -*- coding: utf-8 -*-
{
    'name': "ICTPACK ECTS",

    'summary': """
        IctPack Electronic Cargo Tracking System(ECTS)""",

    'description': """
        IctPack Electronic Cargo Tracking System(ECTS)
    """,

    'author': "IctPack Solutions LTD",
    'website': "https://www.ictpack.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Service',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base','stock','hr'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/product_template_views.xml',
        'views/stock_picking_view.xml',
        'views/ects_trip_views.xml',
        'views/hr_employee_views.xml',
        'views/ects_payment_type_views.xml',
        'views/res_partner_views.xml',
        'views/ects_cargo_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
