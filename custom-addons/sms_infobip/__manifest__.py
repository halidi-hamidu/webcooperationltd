{
    'name': 'Infobip SMS',
    'version': '1.0',
    'summary': 'Send SMS messages using Infobip',
    'category': 'Hidden/Tools',
    'description': """
This module allows using Infobip as a provider for SMS messaging.
The user has to create an account on infobip.com and configure
API credentials to start sending SMS messages.
""",
    'depends': [
        'sms',
    ],
    'data': [
        'views/res_config_settings_views.xml',
        'views/sms_sms_views.xml',
        'wizard/sms_infobip_account_manage_views.xml',
        'security/ir.model.access.csv'
    ],
    'external_dependencies': {
        'python': ['infobip_api_client'],
    },
    'installable': True,
    'author': 'IctPack Solutions LTD',
    'license': 'LGPL-3',
}
