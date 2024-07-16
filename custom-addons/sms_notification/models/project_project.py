from odoo import fields, models, api


class ProjectProject(models.Model):
    _inherit = 'project.project'

    customer_project_id = fields.Many2one('res.partner')
    sale_order_id = fields.Many2one('sale.order')
