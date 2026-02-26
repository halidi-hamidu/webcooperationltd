from odoo import models, fields, tools

class HelpdeskTicketReportAnalysis(models.Model):
    _inherit = 'helpdesk.ticket.report.analysis'

    aggregate_summary = fields.Float(
        string="Total Response Time",
        aggregator="sum",
        readonly=True,
        help="Sum of first response hours and tag transfer response durations"
    )

    def _select(self):
        select_str = super()._select()
        # Add aggregate_summary calculation: first_response_hours + sum of tag transfer response_duration
        select_str = select_str.rstrip()
        if not select_str.endswith(','):
            select_str += ','
        select_str += """
                   (COALESCE(T.first_response_hours, 0) + COALESCE(
                       (SELECT SUM(response_duration) 
                        FROM helpdesk_ticket_tag_transfer 
                        WHERE ticket_id = T.id), 0
                   )) AS aggregate_summary
        """
        return select_str
