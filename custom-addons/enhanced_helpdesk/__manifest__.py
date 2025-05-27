{
    "name": "Enhanced Helpdesk",
    "version": "16.0.1.0.0",
    "summary": "Enhanced Helpdesk Functionality",
    "description": "Adds extended features to the Helpdesk module.",
    "category": "Services/Helpdesk",
    "author": "ictpack",
    "depends": ["base", "helpdesk"],
    "data": [
        "security/ir.model.access.csv",
        "views/helpdesk_ticket_type_views.xml",
        "views/reasons_to_hold_ticket_menu.xml",
        "reports/ticket_report_template.xml",
        "reports/ticket_report_action.xml",
        "views/helpdesk_ticket_form.xml",
        "data/email_template_sla_breach.xml",
        "data/ir_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "enhanced_helpdesk/static/src/js/assignment_alert.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
