from odoo import models, fields, tools


class HelpdeskHoldStatusCountAnalysis(models.Model):
    _name = 'helpdesk.hold.status.count.analysis'
    _description = 'On Hold Status Count Analysis'
    _auto = False
    _order = 'ticket_count desc'

    # Hold Reason Information
    hold_reason_id = fields.Many2one('helpdesk.hold.reason', string='Hold Reason', readonly=True)
    reason_name = fields.Char('Reason', readonly=True)

    # Count Statistics — number of tickets that selected this reason
    ticket_count = fields.Integer('Ticket Count', readonly=True, aggregator="sum",
                                  help='Number of tickets that selected this hold reason')

    # Status
    is_active = fields.Boolean('Active', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    hr.id                                       AS id,
                    hr.id                                       AS hold_reason_id,
                    hr.name                                     AS reason_name,
                    COALESCE(hr.active, TRUE)                   AS is_active,
                    COUNT(rel.helpdesk_ticket_id)               AS ticket_count
                FROM helpdesk_hold_reason hr
                LEFT JOIN helpdesk_hold_reason_helpdesk_ticket_rel rel
                    ON rel.helpdesk_hold_reason_id = hr.id
                GROUP BY hr.id, hr.name, hr.active
                ORDER BY ticket_count DESC, hr.name
            )
        """ % self._table)