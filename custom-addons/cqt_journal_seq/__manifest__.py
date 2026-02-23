# -*- coding: utf-8 -*-
##############################################################################
#
# Cronquotech
# Copyright (C) 2021 (https://cronquotech.odoo.com)
#
##############################################################################
{
    'name': "Journal Sequence in Odoo19",
    'version': '19.0.1.0.0',
    'sequence': 21,
    'website': "https://cronquotech.odoo.com",
    'summary': '''
    Add sequence,
    sequence in journal,
    journal sequence,
    account journal sequence
    ''',
    'description': "Add sequence configuration for journal in odoo 19 same like previous odoo version.",
    'author': 'Cronquotech',
    'category': 'Tools',
    'depends': ['account'],
    'data': [
        'views/account_journal_view.xml',
        'views/account_move_view.xml'
    ],
    'images': [
        'static/description/banner.png',
    ],
    "support": "cronquotech@gmail.com",
    "license": "LGPL-3",
    'price': 9.00,
    'currency': 'USD',
    'installable': True,
    'application': True,
    'auto_install': False
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
