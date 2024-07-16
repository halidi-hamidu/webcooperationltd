# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class kpi_node(models.AbstractModel):
    """
    This is the Abstract Model to manage jstree nodes
    It is used for KPI categories and KPI themselves (the later - on the report view)
    """
    _name = "kpi.node"
    _description = "KPI Node"

    @api.constrains("parent_id")
    def _check_node_recursion(self):
        """
        Constraint for recursion
        """
        if not self._check_recursion():
            raise ValidationError(_("Recursions are not allowed!"))
        return True

    company_id = fields.Many2one("res.company", string="Company")
    sequence = fields.Integer(string="Sequence", default=0)
    active = fields.Boolean(string="Active", default=True)
    description = fields.Text(string="Notes", translate=True)

    @api.model
    def action_get_hierarchy(self, key):
        """
        The method to get hirarchy of KPI targets
        
        Args:
         * key - string - the reference 

        Methods:
         * action_return_nodes of kpi.category
        
        Returns:
         * list of dicts
        """
        result = []
        if key == "kpi_kanban_categories":
            result = self.env["kpi.category"].action_return_nodes()
        elif key == "kpi_items":
            result = self.env["kpi.item"].action_return_nodes()
        elif key == "kpi_tags":
            if self.env.user.has_group("kpi_scorecard.group_kpi_tags"):
                result = self.env["kpi.tag"].action_return_nodes()
        return result
    
    @api.model
    def action_return_nodes(self):
        """
        The method to return nodes in jstree format

        Methods:
         * _return_nodes_recursive

        Returns:
         * list of folders dict with keys:
           ** id
           ** text - folder_name
           ** children - array with the same keys
        """
        res = []
        all_nodes = self.search([])       
        if all_nodes:
            nodes = all_nodes.filtered(lambda fol: not fol.sudo().parent_id or fol.sudo().parent_id not in all_nodes) 
            for node in nodes:
                res.append(node._return_nodes_recursive())
        return res

    def _return_nodes_recursive(self):
        """
        The method to go by all nodes recursively to prepare their list in js_tree format

        Returns:
         * dict

        Extra info:
         * sorted needed to fix unclear bug of zero-sequence element placed to the end
         * Expected singleton
        """
        res = {"text": self.name, "id": self.id}
        child_res = []
        for child in self.child_ids.sorted(lambda ch: ch.sequence):
            child_res.append(child._return_nodes_recursive())
        res.update({"children": child_res})
        return res
