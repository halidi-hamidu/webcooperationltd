# -*- coding: utf-8 -*-
{
    "name": "KPI Balanced Scorecard",
    "version": "16.0.1.1.5",
    "category": "Extra Tools",
    "author": "faOtools",
    "website": "https://faotools.com/apps/16.0/kpi-balanced-scorecard-16-0-kpi-scorecard-713",
    "license": "Other proprietary",
    "application": True,
    "installable": True,
    "auto_install": False,
    "depends": [
        "mail"
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/cron.xml",
        "wizard/kpi_copy_template.xml",
        "views/kpi_measure_item.xml",
        "views/kpi_measure.xml",
        "views/kpi_constant.xml",
        "views/kpi_item.xml",
        "views/kpi_period.xml",
        "views/kpi_category.xml",
        "views/kpi_tag.xml",
        "views/kpi_scorecard_line.xml",
        "views/res_config_settings.xml",
        "views/menu.xml",
        "data/crm_measures.xml",
        "data/sale_measures.xml",
        "data/invoice_measures.xml",
        "data/project_measures.xml"
    ],
    "assets": {
        "web.assets_backend": [
                "kpi_scorecard/static/src/components/jstree_container/*.xml",
                "kpi_scorecard/static/src/components/jstree_container/*.js",
                "kpi_scorecard/static/src/components/kpi_periods/*.xml",
                "kpi_scorecard/static/src/components/kpi_periods/*.js",
                "kpi_scorecard/static/src/components/kpi_navigation/*.xml",
                "kpi_scorecard/static/src/components/kpi_navigation/*.js",
                "kpi_scorecard/static/src/components/kpi_chart/*.xml",
                "kpi_scorecard/static/src/components/kpi_chart/*.js",
                "kpi_scorecard/static/src/components/kpi_chart/*.scss",
                "kpi_scorecard/static/src/components/kpi_report/*.xml",
                "kpi_scorecard/static/src/components/kpi_report/*.js",
                "kpi_scorecard/static/src/views/fields/kpi_formula/*.js",
                "kpi_scorecard/static/src/views/fields/kpi_formula/*.xml",
                "kpi_scorecard/static/src/views/dialogs/kpi_history_dialog/*.js",
                "kpi_scorecard/static/src/views/dialogs/kpi_history_dialog/*.xml",
                "kpi_scorecard/static/src/views/**/*.xml",
                "kpi_scorecard/static/src/views/**/*.js",
                "kpi_scorecard/static/src/views/**/*.scss"
        ]
},
    "demo": [
        
    ],
    "external_dependencies": {},
    "summary": "The tool to set up KPI targets and control their fulfillment by periods. KPI dashboards. Dashboard designer. KPI charts. Odoo dashboards. Analytic dashboards. Create dashboards. Customize dashboards. Chart Graphs. Key performance indicators. Dynamic KPIs. Smart goals.",
    "description": """For the full details look at static/description/index.html
* Features * 
- Real-time control and historical trends
- Drag-and-drop formulas for KPIs
- Shared KPIs and self-control
- KPI settings to process Odoo data
#odootools_proprietary""",
    "images": [
        "static/description/main.png"
    ],
    "price": "198.0",
    "currency": "EUR",
    "live_test_url": "https://faotools.com/my/tickets/newticket?&url_app_id=138&ticket_version=16.0&url_type_id=3",
}