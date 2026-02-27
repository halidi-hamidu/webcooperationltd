from odoo import models, fields, tools


class HelpdeskHoldAnalysis(models.Model):
    _name = 'helpdesk.hold.analysis'
    _description = "Helpdesk Hold Analysis Report"
    _auto = False
    _order = 'hold_start DESC'

    # Ticket Information
    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', readonly=True)
    ticket_name = fields.Char(string='Ticket Name', readonly=True)
    ticket_stage_id = fields.Many2one('helpdesk.stage', string='Current Stage', readonly=True)
    ticket_team_id = fields.Many2one('helpdesk.team', string='Ticket Team', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    assigned_user_id = fields.Many2one('res.users', string='Assigned To', readonly=True)
    create_date = fields.Datetime("Ticket Created On", readonly=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Medium'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', readonly=True)

    # Hold Log Information (from helpdesk.ticket.hold.log — real SLA source of truth)
    hold_start = fields.Datetime('Hold Start', readonly=True)
    hold_end = fields.Datetime('Hold End', readonly=True)
    hold_duration_hours = fields.Float(
        'Hold Duration (Hours)', readonly=True, aggregator="avg",
        help='Actual time the ticket was paused in On Hold stage'
    )
    total_hold_hours = fields.Float(
        'Total Hold Hours (Ticket)', readonly=True, aggregator="sum",
        help='Cumulative hold time across all hold periods for this ticket'
    )
    hold_reasons_text = fields.Char('Hold Reasons', readonly=True)

    # Status
    is_currently_on_hold = fields.Boolean('Currently on Hold', readonly=True)
    hold_count = fields.Integer(
        'Hold Count', readonly=True, aggregator="sum",
        help='Number of times this hold log entry exists (1 per period)'
    )

    # SLA Impact
    sla_deadline = fields.Datetime('Original SLA Deadline', readonly=True)
    sla_adjusted_deadline = fields.Datetime('Adjusted SLA Deadline', readonly=True)
    sla_deadline_extended_hours = fields.Float(
        'SLA Extension (Hours)', readonly=True, aggregator="avg",
        help='How many hours the SLA deadline was pushed forward due to holds'
    )
    sla_breached = fields.Boolean('SLA Breached', readonly=True)
    sla_status = fields.Selection([
        ('safe', 'Safe'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('breached', 'Breached'),
        ('paused', 'Paused'),
    ], string='SLA Status', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    hl.id AS id,

                    -- Ticket core info
                    t.id                        AS ticket_id,
                    t.name                      AS ticket_name,
                    t.stage_id                  AS ticket_stage_id,
                    t.team_id                   AS ticket_team_id,
                    t.partner_id                AS partner_id,
                    t.user_id                   AS assigned_user_id,
                    t.create_date               AS create_date,
                    t.priority                  AS priority,

                    -- Actual hold log timestamps (source of truth for SLA)
                    hl.start_time               AS hold_start,
                    hl.end_time                 AS hold_end,
                    hl.duration_hours           AS hold_duration_hours,
                    hl.reason                   AS hold_reasons_text,

                    -- Cumulative hold hours for the whole ticket
                    (
                        SELECT COALESCE(SUM(hl2.duration_hours), 0)
                        FROM helpdesk_ticket_hold_log hl2
                        WHERE hl2.ticket_id = t.id
                    )                           AS total_hold_hours,

                    -- Is this specific hold period still open?
                    CASE
                        WHEN hl.end_time IS NULL THEN TRUE
                        ELSE FALSE
                    END                         AS is_currently_on_hold,

                    1                           AS hold_count,

                    -- SLA fields
                    t.sla_deadline              AS sla_deadline,

                    -- Adjusted deadline = original deadline + total hold time
                    CASE
                        WHEN t.sla_deadline IS NOT NULL THEN
                            t.sla_deadline + (
                                COALESCE((
                                    SELECT SUM(hl3.duration_hours)
                                    FROM helpdesk_ticket_hold_log hl3
                                    WHERE hl3.ticket_id = t.id
                                ), 0) * INTERVAL '1 hour'
                            )
                        ELSE NULL
                    END                         AS sla_adjusted_deadline,

                    -- Extension = total hold hours added to SLA
                    COALESCE((
                        SELECT SUM(hl4.duration_hours)
                        FROM helpdesk_ticket_hold_log hl4
                        WHERE hl4.ticket_id = t.id
                    ), 0)                       AS sla_deadline_extended_hours,

                    t.sla_breached              AS sla_breached,
                    t.sla_status                AS sla_status

                FROM helpdesk_ticket_hold_log hl
                JOIN helpdesk_ticket t ON t.id = hl.ticket_id
            )
        """ % self._table)