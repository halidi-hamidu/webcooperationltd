# -*- coding: utf-8 -*-

from odoo import _, fields, models


class res_config_settings(models.TransientModel):
    """
    The model to keep settings of business appointments on website
    """
    _inherit = "res.config.settings"

    kpi_history_tolerance = fields.Integer(
        string="History Tolerance", 
        config_parameter="kpi_scorecard.kpi_history_tolerance",
        default=3
    )
    show_kpi_help = fields.Boolean(string="Show Help", config_parameter="kpi_scorecard.show_kpi_help")
    group_kpi_tags = fields.Boolean("KPI tags", implied_group="kpi_scorecard.group_kpi_tags")

    def action_open_kpi_cron(self):
        """
        The method to open ir.cron of kpi update

        Returns:
         * action dict

        Extra info:
         * Expected singleton
        """
        cron_id = self.sudo().env.ref("kpi_scorecard.cron_recalculate_kpi_periods", False)
        if cron_id:
            return {
                "res_id": cron_id.id,
                "name": _("Job: Calculate KPIs"),
                "type": "ir.actions.act_window",
                "res_model": "ir.cron",
                "view_mode": "form",
                "target": "new",
            }
