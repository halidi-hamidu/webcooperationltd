{
    "name": "Web Selcom Integration",
    "summary": "Selcom payment gateway integration: checkout orders, till aliases, webhooks",
    "version": "1.0.0",
    "category": "Accounting/Payment",
    "author": "WebCoP",
    "license": "LGPL-3",
    "depends": [
        "base",
        "account",
        "payment",  # payment acquirer pipeline integration point
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/selcom_views.xml",
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "application": False,
}
