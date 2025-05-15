{
    'name': 'Enhanced Helpdesk',
    'version': '16.0.1.0.0',
    'summary': 'Enhanced Helpdesk Functionality',
    'description': 'Adds extended features to the Helpdesk module.',
    'category': 'Services/Helpdesk',
    'author': 'ictpack',
    'depends': ['base', 'helpdesk'],
    'data': [
        'views/helpdesk_ticket_views.xml',
        'views/helpdesk_ticket_type_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
