# -*- coding: utf-8 -*-
# from odoo import http


# class FleetTraccar(http.Controller):
#     @http.route('/fleet_traccar/fleet_traccar', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/fleet_traccar/fleet_traccar/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('fleet_traccar.listing', {
#             'root': '/fleet_traccar/fleet_traccar',
#             'objects': http.request.env['fleet_traccar.fleet_traccar'].search([]),
#         })

#     @http.route('/fleet_traccar/fleet_traccar/objects/<model("fleet_traccar.fleet_traccar"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('fleet_traccar.object', {
#             'object': obj
#         })
