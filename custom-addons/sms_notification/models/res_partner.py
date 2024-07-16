# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    project_ids = fields.One2many('project.project', 'customer_project_id')
