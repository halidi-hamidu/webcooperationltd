# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright 2019 EquickERP
#
##############################################################################

{
    'name': "Allow Cancel Journal Entry",
    'category': 'Accounting',
    'version': '16.0.1.0',
    'author': 'Equick ERP',
    'description': """
        This Module allows user to Cancel journal entries based on security access rights.
        * Allows user to Cancel Journal entries, Invoices/Bills and Payments based on users access rights.
        * User Wise Configuration.
    """,
    'summary': """ This Module allows user to Cancel journal entries based on security access rights.| cancel Journal | cancel invoice | cancel bill | cancel account entry | cancel journal entry | cancel account journal entry. """,
    'depends': ['base', 'account'],
    'price': 10,
    'currency': 'EUR',
    'license': 'OPL-1',
    'website': "",
    'data': [
        'security/security.xml',
        'views/journal_view.xml'
    ],
    'images': ['static/description/main_screenshot.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: