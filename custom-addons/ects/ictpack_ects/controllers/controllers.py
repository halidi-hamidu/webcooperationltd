# -*- coding: utf-8 -*-
# from odoo import http


# class IctpackEcts(http.Controller):
#     @http.route('/ictpack_ects/ictpack_ects', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/ictpack_ects/ictpack_ects/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('ictpack_ects.listing', {
#             'root': '/ictpack_ects/ictpack_ects',
#             'objects': http.request.env['ictpack_ects.ictpack_ects'].search([]),
#         })

#     @http.route('/ictpack_ects/ictpack_ects/objects/<model("ictpack_ects.ictpack_ects"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('ictpack_ects.object', {
#             'object': obj
#         })
