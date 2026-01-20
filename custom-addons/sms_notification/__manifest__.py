# -*- coding: utf-8 -*-
{
    'name': "SMS NOTIFICATIONS",

    'summary': """
        Automated SMS notifications for invoices""",

    'description': """
        SMS Invoice Notifications Module
        ==================================
        
        This module provides automated SMS notifications for invoice reminders:
        
        Features:
        ---------
        * Automated invoice reminders at configurable intervals
          - 15 days before invoice date
          - 7 days after invoice date
          - Overdue invoice reminders
        * Integration with sms_infobip module for reliable SMS delivery
        * Template-based SMS messages
        * Delivery status tracking
        * Manual and scheduled sending options
        
        For Mass SMS Campaigns:
        -----------------------
        Use Odoo's built-in SMS Marketing (mass_mailing_sms) module for:
        * Marketing campaigns with analytics
        * Advanced customer segmentation
        * A/B testing
        * Scheduled campaigns
        * Campaign performance tracking
        
        Configuration:
        --------------
        1. Install sms_infobip module first
        2. Configure Infobip credentials in Settings > General Settings > Integrations
        3. Create SMS templates as needed
        4. Enable scheduled actions for automated sending
    """,

    'author': "IctPack Solutions LTD",
    'website': "https://www.ictpack.com",
    'category': 'Sales',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['sms', 'sms_infobip', 'account', 'sale', 'custom_ictpack'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/sms_views.xml',
        'views/sale_order_views.xml',
        'views/account_move.xml',
        'views/res_partner_views.xml',
        'data/sms_templates.xml',
        'data/ir_cron_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [],
    'auto_install': False,
    'installable': True,
    'application': True,
}
