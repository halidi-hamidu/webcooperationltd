# -*- coding: utf-8 -*-
{
    'name': "ICTPACK VTS",

    'summary': """
        Vehicle Tracking Services (VTS)
        """,

    'description': """
        Vehicle Tracking Services (VTS)
    """,

    'author': "IctPack Solutions LTD",
    'website': "https://www.ictpack.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Service',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': [
        'hr',
        'hr_attendance',
        'base',
        'stock',
        'project',
        'web',
        'sale',
        'board',
        'helpdesk',
        'fleet',
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/notification_types.xml',
        'views/vts_job_card_view.xml',
        'views/hr_employee_views.xml',
        'views/product_template_view.xml',
        # 'views/stock_picking_view.xml',
        'views/project_view.xml',
        'views/vts_task_stage_view.xml',
        'views/vts_checklist_config_view.xml',
        'views/vts_attendance_view.xml',
        'views/report_action.xml',
        'views/report_job_card_template.xml',
        'views/vts_daily_checkup_list.xml',
        'views/reset_password_template.xml',
        'views/helpdesk_ticket_view.xml',
        'views/create_ticket_wizard_view.xml',
        'views/vts_configurations_views.xml',
        # 'views/portal_my_jobcard.xml',

    ],
    'assets': {
        
    },
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
