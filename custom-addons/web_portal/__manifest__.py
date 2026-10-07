{
    "name": "Web Portal - Custom Dashboard",
    "summary": "Custom Dark Mode Dashboard for Fleet and Invoices Customer Portal",
    "version": "1.0.0",
    "category": "Website/Portal",
    "author": "WebCoP",
    "license": "LGPL-3",
    "depends": [
        "portal",
        "fleet",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/web_portal_security.xml",
        "views/portal_templates.xml",
        "views/portal_detail_templates.xml",
        "views/navbar_layout.xml",
    ],
    "installable": True,
    "application": False,
}
