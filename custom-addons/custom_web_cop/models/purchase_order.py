# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    READONLY_STATES = {
        'to approve': [('readonly', True)],
        'co approve': [('readonly', True)],
        'purchase': [('readonly', True)],
        'done': [('readonly', True)],
        'cancel': [('readonly', True)],
    }

    currency_id = fields.Many2one('res.currency', 'Currency', required=True, states=READONLY_STATES, \
                                  default=lambda self: self.env.user.company_id.currency_id.id)

    partner_id = fields.Many2one('res.partner', string='Vendor', required=True, states=READONLY_STATES,
                                 change_default=True, track_visibility='always')

    partner_ref = fields.Char('Vendor Reference', copy=False, \
                              help="Reference of the sales order or bid sent by the vendor. "
                                   "It's used to do the matching when you receive the "
                                   "products as this reference is usually written on the "
                                   "delivery order sent by your vendor.", states=READONLY_STATES)

    date_order = fields.Datetime('Order Date', required=True, states=READONLY_STATES, index=True, copy=False,
                                 default=fields.Datetime.now, \
                                 help="Depicts the date where the Quotation should be validated and converted into a purchase order.")

    order_line = fields.One2many('purchase.order.line', 'order_id', string='Order Lines', states=READONLY_STATES,
                                 copy=True)

    product_id = fields.Many2one('product.product', related='order_line.product_id', states=READONLY_STATES,
                                 string='Product')

