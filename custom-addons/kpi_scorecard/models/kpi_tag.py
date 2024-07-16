#coding: utf-8

from odoo import api, fields, models


class kpi_tag(models.Model):
    """
    The model to structure KPIs and targets
    """
    _name = "kpi.tag"
    _inherit = ["kpi.node"]
    _description = "KPI Tag"

    def _inverse_active(self):
        """
        Inverse method for active to deactivate all child tags
        """
        for tag in self:
            if not tag.active:
                for child in tag.child_ids:
                    child.active = False

    name = fields.Char(string="Name", required=True, translate=True)
    parent_id = fields.Many2one("kpi.tag", string="Parent Tag")
    child_ids = fields.One2many("kpi.tag", "parent_id", string="Child Tags")
    active = fields.Boolean(inverse=_inverse_active)
