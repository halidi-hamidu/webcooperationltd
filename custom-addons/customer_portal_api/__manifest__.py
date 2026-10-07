{
    "name": "Customer Portal API",
    "summary": "Secure REST API exposing customer portal functionality (auth, projects, invoices) for mobile/external apps",
    "version": "1.0.0",
    "category": "Services/API",
    "author": "WebCoP",
    "license": "LGPL-3",
    "depends": [
        "base",
        "project",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
}
