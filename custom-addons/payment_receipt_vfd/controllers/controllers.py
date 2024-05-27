# -*- coding: utf-8 -*-
# from odoo import http


# class PaymentReceiptVfd(http.Controller):
#     @http.route('/payment_receipt_vfd/payment_receipt_vfd/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/payment_receipt_vfd/payment_receipt_vfd/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('payment_receipt_vfd.listing', {
#             'root': '/payment_receipt_vfd/payment_receipt_vfd',
#             'objects': http.request.env['payment_receipt_vfd.payment_receipt_vfd'].search([]),
#         })

#     @http.route('/payment_receipt_vfd/payment_receipt_vfd/objects/<model("payment_receipt_vfd.payment_receipt_vfd"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('payment_receipt_vfd.object', {
#             'object': obj
#         })
