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
          - New registration notifications
          - 30 days before invoice date
          - 15 days before invoice date
          - Due date reminders
          - 7 days after invoice date
          - Above 7 days after due date
        * Integration with mass_mailing_sms and sms_infobip for reliable SMS delivery
        * Template-based SMS messages via mailing.mailing model
        * Delivery status tracking with Infobip integration
        * Automated SMS queue generation via scheduled actions
        * Full SMS Marketing features (analytics, segmentation, A/B testing)
        
        Configuration:
        --------------
        1. Install sms_infobip and mass_mailing_sms modules
        2. Configure Infobip credentials in Settings > General Settings > Integrations
        3. Create SMS templates as needed
        4. Enable scheduled actions for automated SMS generation
    """,

    'author': "IctPack Solutions LTD",
    'website': "https://www.ictpack.com",
    'category': 'Sales',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['sms', 'sms_infobip', 'mass_mailing_sms', 'account', 'sale', 'custom_ictpack'],

    # always loaded
    'data': [
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
