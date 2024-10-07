# -*- coding: utf-8 -*-
{
    'name': "Odoo Fleet with Traccar",

    'summary': """
        Track your Fleet from Odoo by Integrating with Traccar""",

    'description': """
       Fleet Traccar allows you to track the vehicle movements of all your cars via Traccar server. 
       Also, the module enables you to manage tracking data and reports it via Odoo. 
       Also, check the summary,events,trips for a particular custom period
    """,

    'author': "IctPack Solutions LTD",
    'website': "http://www.ictpack.com",

    #Categories can be used to filter modules in modules listing
    #Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    #for the full list
    'category': 'Human Resources/Fleet',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','fleet'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/fleet_cars_data.xml',
        'views/res_config_settings_views.xml',
        'views/fleet_event_views.xml',
        'views/fleet_stops_views.xml',
        'views/fleet_summary_views.xml',
        'views/fleet_trips_views.xml',
        'views/fleet_vehicle_model.xml',
        'views/fleet_vehicle_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
