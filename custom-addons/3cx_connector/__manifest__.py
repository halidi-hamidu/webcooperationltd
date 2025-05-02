{
    'name': '3CX Connector',
    'version': '16.0.1.0.0',
    'summary': '3CX Telephony Integration',
    'description': """
        Complete integration between Odoo CRM and 3CX phone system
        - Contact synchronization
        - Screen pop on incoming calls
        - Call logging and history
        - Click-to-call functionality
    """,
    'author': 'IctPack Solutions LTD',
    'website': 'https://ictpack.com',
    'category': 'CRM',
    'depends': ['base', 'crm', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/3cx_config_data.xml',
        'data/call_metrics_cron.xml',
        'views/3cx_config_views.xml',
        'views/call_log_views.xml',
        'views/res_partner_views.xml',
        'views/call_metrics_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            '3cx_connector/static/src/js/duration_formatter.js',
            #'3cx_connector/static/src/css/screen_pop.css',
            #'3cx_connector/static/src/js/screen_pop.js',
            #'3cx_connector/static/src/xml/screen_pop_templates.xml',
        ],
    },
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}