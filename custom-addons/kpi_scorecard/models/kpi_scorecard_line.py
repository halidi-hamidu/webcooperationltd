#coding: utf-8

from odoo import _, api, fields, models


class kpi_scorecard_line(models.Model):
    """
    The model that introduces KPI targets
    """
    _name = "kpi.scorecard.line"
    _inherit = "kpi.help"
    _description = "KPI Target"
    _rec_name = "kpi_id"

    @api.depends("kpi_id", "kpi_id.tag_ids")
    def _compute_tag_ids(self):
        """
        Compute method for tag_ids
        """
        for line in self:
            line.tag_ids = [(6, 0, line.kpi_id.tag_ids.ids)]

    @api.depends("target_value", "actual_value", "computation_error", "kpi_id", "kpi_id.result_appearance", 
        "kpi_id.result_preffix", "kpi_id.result_suffix", "kpi_id.result_type")
    def _compute_formatted_actual_value(self):
        """
        Compute method for formatted_actual_value, result, formatted_target_value

        Methods:
         * _return_formated_appearance of kpi.item
        """
        for line in self:
            kpi_id = line.kpi_id
            company_currency = line.period_id.company_id.currency_id
            if line.computation_error:
                line.formatted_actual_value = _("N/A")
                line.result = "error"
                line.formatted_target_value = kpi_id._return_formated_appearance(
                    line.target_value, novalue_change=True, currency=company_currency,
                )
                line.progress_way = -1
            else:
                actual_value = line.actual_value
                line.formatted_actual_value = kpi_id._return_formated_appearance(
                    line.actual_value, novalue_change=False, currency=company_currency,
                )
                line.formatted_target_value = kpi_id._return_formated_appearance(
                    line.target_value, novalue_change=True, currency=company_currency,
                )
                result_type = kpi_id.result_type
                actual_value = line.kpi_id.result_appearance == "percentage" and (actual_value * 100) or actual_value
                bigger_result = actual_value >= line.target_value
                if result_type == "more":
                    line.result = bigger_result and "success" or "failure"
                elif result_type == "less":
                    line.result = bigger_result and "failure" or "success"
                
                progress_way = -1
                if line.target_value > 0 and actual_value > 0:
                    progress_way = round(actual_value/line.target_value, 2)*100 or 0.0001
                line.progress_way = progress_way

    @api.depends("period_id", "period_id.line_ids", "period_id.line_ids.kpi_id", "period_id.line_ids.kpi_id.sequence", 
        "period_id.line_ids.kpi_id.all_parent_ids")
    def _compute_sequence(self):
        """
        The method to re-compute sequence, parent_id for lines
        """
        periods = self.mapped("period_id")
        for period in periods:
            res_hierarchy = period.line_ids.action_get_kpis_hierarchy() 
            cur_sequence = 0
            for line_dict in res_hierarchy:
                line = line_dict.get("line")
                line.sequence = cur_sequence
                parent = line_dict.get("parent")
                line.all_parents =  parent and "{}{}".format(
                    parent.id, parent.all_parents and "{}".format("," + parent.all_parents) or ""
                ) or False
                cur_sequence += 1

    @api.depends("kpi_id", "kpi_id.edit_access_user_ids")
    def _compute_edit_rights(self):
        """
        Compute method for edit_rights
        """
        active_user = self.env.user
        admin_rights = active_user.has_group("kpi_scorecard.group_kpi_admin")
        for line in self:
            line.edit_rights = admin_rights or active_user in line.kpi_id.edit_access_user_ids or False

    kpi_id = fields.Many2one("kpi.item", string="KPI", required=True)
    category_id = fields.Many2one("kpi.category", related="kpi_id.category_id", store=True)
    tag_ids = fields.Many2many("kpi.tag", compute=_compute_tag_ids, store=True)
    description = fields.Text(related="kpi_id.description", store=True)
    period_id = fields.Many2one("kpi.period", string="Period", ondelete="cascade")
    date_start = fields.Date(
        "Period Start",
        related="period_id.date_start",
        store=True,
        compute_sudo=True,
        related_sudo=True,
    )  
    date_end = fields.Date(
        "Period End",
        related="period_id.date_end",
        store=True,
        compute_sudo=True,
        related_sudo=True,
    )
    result_type = fields.Selection(
        related="kpi_id.result_type",
        store=True,
        compute_sudo=True,
        related_sudo=True,
    )
    target_value = fields.Float(string="Target Value")
    formatted_target_value = fields.Char(
        string="Target",
        compute=_compute_formatted_actual_value,
        compute_sudo=True,
        store=True,
    )
    actual_value = fields.Float(string="Actual Value")
    computation_error = fields.Char(string="Logs")
    formatted_actual_value = fields.Char(
        string="Actual",
        compute=_compute_formatted_actual_value,
        compute_sudo=True,
        store=True,
    )
    progress_way = fields.Float(
        string="Progress",
        compute=_compute_formatted_actual_value,
        compute_sudo=True,
        store=True,        
    )
    result = fields.Selection(
        [
            ("success", "Success"),
            ("failure", "Failure"),
            ("error", "Error"),
        ],
        compute=_compute_formatted_actual_value,
        compute_sudo=True,
        store=True,
    )
    sequence = fields.Integer(
        string="Sequence",
        compute=_compute_sequence,
        compute_sudo=True,
        store=True,
    )
    all_parents = fields.Char(
        string="All Parents",
        compute=_compute_sequence,
        compute_sudo=True,
        store=True,
    )
    edit_rights = fields.Boolean("Active User Editor", compute=_compute_edit_rights)
    company_id = fields.Many2one(
        related="period_id.company_id",
        store=True,
        compute_sudo=True,
        related_sudo=True,
    )
    period_length = fields.Float(
        related="period_id.period_length",
        store=True,
        compute_sudo=True,
        related_sudo=True,
    )

    _order = "sequence, id"

    _sql_constraints = [
        ("period_kpi_uniq", "unique(period_id, kpi_id)", _("The target for this KPI is already set for this period!"))
    ]

    def name_get(self):
        """
        Overloading the method to make a name, since it doesn't have own
        """
        result = []
        for line in self:
            name = "{} ({})".format(line.kpi_id.name, line.period_id.name_get()[0][1])
            result.append((line.id, name))
        return result

    def action_get_kpis_hierarchy(self):
        """
        The method to get hirarchy of KPI targets

        Methods:
         * _get_levels_recursively
        
        Returns:
         * list of dicts
        """
        result = []
        kpi_ids = self.mapped("kpi_id")
        if kpi_ids:
            kpi_ids = kpi_ids.sorted("sequence")
            kpi_lines_dict = {line.kpi_id.id: line for line in self} 
            parent_kpis = kpi_ids.filtered(lambda kpi: not kpi.parent_id or kpi.parent_id.id not in kpi_ids.ids)
            for parent_kpi in parent_kpis:
                line_id = kpi_lines_dict.get(parent_kpi.id)
                result += line_id._get_levels_recursively(parent_kpi, kpi_ids.ids, kpi_lines_dict, False)
        return result

    def _represent_targets_for_graph(self):
        """
        The method to prepare dict of values for targets graph
        
        Returns:
         * list of dicts:
          ** kpi_id - kpi.item object
          ** date - str
          ** value - float
          ** target_value - float
          ** background - str (hex/rgb color for column)
        """
        lang = self._context.get("lang")
        lang_date_format = "%m/%d/%Y"
        if lang:
            record_lang = self.env["res.lang"].search([("code", "=", lang)], limit=1)
            lang_date_format = record_lang.date_format
        return self and self.mapped(lambda target: {
            "kpi_id": target.kpi_id,
            "date": target.period_id.date_end.strftime(lang_date_format),
            "value": not target.computation_error and target.kpi_id._return_rounded_value(target.actual_value, False) \
                or 0,
            "target_value": target.target_value,
            "background": target.result == "success" and "#008818" or "#d23f3a",
        }) or []

    def _get_levels_recursively(self, parent_kpi, all_kpis, kpi_lines_dict, parent_line=False,):
        """
        The recursion method to get child kpi one by one
    
        Args:
         * parent_kpi - kpi.item record
         * all_kpis - list of ints
         * kpi_lines_dict - dict of relations kpi.scorecard.line (id - int) - kpi.item (id - int)
         * parent_line - id of parent

        Methods:
         * _get_value_dict

        Returns:
         * list of dicts

        Extra info:
         * Expected singleton
        """
        result = [self._get_value_dict(all_kpis, parent_line)]
        child_ids = self.kpi_id.child_ids
        for child_kpi in child_ids:
            child_kpi_id = child_kpi.id
            if child_kpi_id in all_kpis:
                line_id = kpi_lines_dict.get(child_kpi_id)
                result += line_id._get_levels_recursively(child_kpi, all_kpis, kpi_lines_dict, self)
        return result

    def _get_value_dict(self, all_kpis, parent_line=False):
        """
        The method to prepare values dict of js

        Args:
         * all_kpis - list of ints
         * parent_line - kpi.scorecard.line -parent

        Returns:
         * list of dict
           ** line - kpi.scorecard.line
           ** parent - int of parent if exist, False otherwise

        Extra info:
         * Expected singleton
        """
        return {"line": self, "parent": parent_line}

    def _get_xls_table(self):
        """
        The method to prepare dict of values for xls row

        Args:
         * spaces - str - to add at the beginning of the name

        Methods:
         * _return_xls_formatting - of kpi.item
    
        Returns:
         * dict
        """
        result = {}
        row = 2
        previous_kpis = {}
        for line in self:
            parent_id = line.kpi_id.parent_id.id
            level = previous_kpis.get(parent_id) is not None and previous_kpis.get(parent_id) + 1 or 0
            previous_kpis.update({line.kpi_id.id: level})
            description = line.description or ""
            target_value = line.target_value
            actual_value = line.actual_value
            overall_style = { 
                "color": line.result == "success" and "black" or line.result == "failure" and "red" or "orange"
            }
            if line.computation_error:
                target_value = 0
                actual_value = 0
                description = "{} {}".format(line.computation_error, description)
                overall_style.update({"color": "orange"})
            target_value = line.kpi_id._return_xls_formatting(line.target_value, False)
            actual_value = line.kpi_id._return_xls_formatting(line.actual_value, True)
            num_style = overall_style.copy()
            num_style.update({
                "align": "center",
            })
            if line.kpi_id.result_appearance == "percentage":
                num_style.update({"num_format": 10}),
            overall_style.update({
                "valign": "vjustify",
            })
            result.update({
                "A{}".format(row): {"value": line.kpi_id.name, "style": overall_style, "level": level},
                "B{}".format(row): {"value": target_value, "style": num_style},
                "C{}".format(row): {"value": actual_value, "style": num_style},
                "D{}".format(row): {"value": description, "style": overall_style},
            })      
            row += 1
        return result
