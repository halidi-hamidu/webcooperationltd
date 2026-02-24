# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################
{
    "name": "Custom IctPack Module",
    "summary": "Invoice UI, Sales Order, Quotations "
               "Receipt Printouts.",
    "version": "1.0.0",
    "author": "IctPack Solutions LTD",
    "license": "OPL-1",
    "support": "projects@ictpack.com",
    "category": "Tools",
    "website": "https://ictpack.com",
    "depends": [
        "account",
        "sale",
        "sale_crm",
        "purchase",
        "project",
        "stock",
        'approvals',
        # "contract",
         'hr', 
         'hr_payroll'
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/payment_reference_warning_wizard_view.xml",
        "views/asset_label_generator_wizard_view.xml",
        "views/account_move_view.xml",
        # "views/account_asset_views.xml",
        "views/sale_order_view.xml",
        "views/company_form_view.xml",
        "views/partner_form_view.xml",
        "views/purchase_form_view.xml",
        "views/account_payment.xml",
        "views/project_views.xml",
        # "views/hr_contract.xml",
        "views/stock_picking_form_view.xml",
        # "views/account_analytic_account_view.xml",
        # "views/contract.xml",
        # "views/contract_line.xml",
        "views/internal_layout.xml",
        "views/report_external_layout_views.xml",
        "views/report_invoice.xml",
        "views/report_sale.xml",
        "views/report_purchase.xml",
        "views/approval_request_views.xml",
        "views/hr_version.xml",
    ],
    "installable": True,
    "maintainers": ["ictpack"],
    "images": [
        "static/description/invoicensales.png"
    ],
}
