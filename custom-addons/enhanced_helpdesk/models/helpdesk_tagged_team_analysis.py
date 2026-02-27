from odoo import models, fields, tools


class HelpdeskTaggedTeamAnalysis(models.Model):
    _name = 'helpdesk.tagged.team.analysis'
    _description = "Tagged Team Response Analysis"
    _auto = False
    _order = 'ticket_id DESC'

    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', readonly=True)
    ticket_name = fields.Char(string='Ticket Name', readonly=True)
    team_id = fields.Many2one('helpdesk.team', string='Tagged Team', readonly=True)
    total_response_time = fields.Float(
        string='Total Response Time (Hours)', 
        aggregator="sum",
        readonly=True,
        help='Sum of all response times for tagged users in this team'
    )
    tag_count = fields.Integer(
        string='Number of Tags',
        aggregator="sum",
        readonly=True,
        help='Number of times users from this team were tagged'
    )
    avg_response_time = fields.Float(
        string='Average Response Time (Hours)',
        aggregator="avg",
        readonly=True,
        help='Average response time per tag for this team'
    )
    total_resolution_time = fields.Float(
        string='Total Resolution Time (Hours)', 
        aggregator="sum",
        readonly=True,
        help='Sum of all resolution times for tagged users in this team'
    )
    avg_resolution_time = fields.Float(
        string='Average Resolution Time (Hours)',
        aggregator="avg",
        readonly=True,
        help='Average resolution time per closed assignment for this team'
    )
    closed_count = fields.Integer(
        string='Closed Assignments',
        aggregator="sum",
        readonly=True,
        help='Number of assignments that were closed'
    )
    ticket_stage_id = fields.Many2one('helpdesk.stage', string='Ticket Stage', readonly=True)
    ticket_team_id = fields.Many2one('helpdesk.team', string='Ticket Team', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    user_id = fields.Many2one('res.users', string='Assigned To', readonly=True)
    contributor_id = fields.Many2one('res.users', string='Contributor', readonly=True)
    contributor_type = fields.Char(string='Contribution Type', readonly=True)
    hold_count = fields.Integer(string='Hold Count', readonly=True, aggregator="sum")
    total_logged_hours = fields.Float(string='Total Logged Hours', readonly=True, aggregator="sum")

    # ── Collaboration Score Metrics ──────────────────────────────────────────
    # All rates are stored as 0–100 percentages per row
    participation_rate = fields.Float(
        string='Participation Rate % (PR)',
        aggregator="avg",
        readonly=True,
        digits=(5, 2),
        help='(Responded Tags / Total Active Tags) × 100'
    )
    resolution_rate = fields.Float(
        string='Resolution Rate % (CR)',
        aggregator="avg",
        readonly=True,
        digits=(5, 2),
        help='(Completed Tasks / Total Active Tags) × 100'
    )
    sla_compliance_rate = fields.Float(
        string='SLA Compliance Rate % (SLA%)',
        aggregator="avg",
        readonly=True,
        digits=(5, 2),
        help='(Responses Within SLA / Total Active Tags) × 100'
    )
    rework_rate = fields.Float(
        string='Rework Rate % (Penalty)',
        aggregator="avg",
        readonly=True,
        digits=(5, 2),
        help='(Re-Tagged Cases / Total Active Tags) × 100'
    )
    collaboration_score = fields.Float(
        string='Collaboration Score % (CTCS)',
        aggregator="avg",
        readonly=True,
        digits=(5, 2),
        help='CTCS = 0.35×PR + 0.35×CR + 0.20×SLA% − 0.10×Rework%'
    )
    performance_rating = fields.Selection([
        ('excellent', '⭐ Excellent (90–100%)'),
        ('stable',    '✅ Stable (80–89%)'),
        ('at_risk',   '⚠️ At Risk (70–79%)'),
        ('critical',  '🔴 Critical (<70%)'),
    ], string='Performance Rating', readonly=True,
       help='Based on Collaboration Score: Excellent≥90, Stable≥80, At Risk≥70, Critical<70'
    )
    performance_rating_num = fields.Integer(
        string='Performance Rating (Score)',
        readonly=True,
        aggregator="avg",
        help='4=Excellent, 3=Stable, 2=At Risk, 1=Critical'
    )

    # Descriptive time fields - stored for pivot grouping
    total_response_time_desc = fields.Char(string='Total Response Time', readonly=True)
    avg_response_time_desc = fields.Char(string='Average Response Time', readonly=True)
    total_resolution_time_desc = fields.Char(string='Total Resolution Time', readonly=True)
    avg_resolution_time_desc = fields.Char(string='Average Resolution Time', readonly=True)
    
    create_date = fields.Datetime("Created On", readonly=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Medium'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', readonly=True)
    
    def _format_hours_to_desc(self, hours):
        """Format hours to descriptive text with days, hours, minutes, seconds"""
        if not hours:
            return "No time"
        
        total_seconds = int(hours * 3600)
        
        if total_seconds < 60:
            return f"{total_seconds} sec"
        
        days = total_seconds // 86400
        remaining_seconds = total_seconds % 86400
        hours_part = remaining_seconds // 3600
        remaining_seconds %= 3600
        minutes_part = remaining_seconds // 60
        seconds_part = remaining_seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours_part > 0:
            parts.append(f"{hours_part}h")
        if minutes_part > 0:
            parts.append(f"{minutes_part}m")
        if seconds_part > 0 and len(parts) < 2:  # Only show seconds if not too many parts
            parts.append(f"{seconds_part}s")
        
        return " ".join(parts) if parts else "0 sec"

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        
        # Create PostgreSQL function for time formatting
        self.env.cr.execute("""
            CREATE OR REPLACE FUNCTION format_hours_to_desc(hours FLOAT) RETURNS TEXT AS $func$
            DECLARE
                total_seconds INTEGER;
                days INTEGER;
                hours_part INTEGER;
                minutes_part INTEGER;
                seconds_part INTEGER;
                remaining_seconds INTEGER;
                result_parts TEXT[];
            BEGIN
                IF hours IS NULL OR hours = 0 THEN
                    RETURN 'No time';
                END IF;
                
                total_seconds := (hours * 3600)::INTEGER;
                
                IF total_seconds < 60 THEN
                    RETURN total_seconds || ' sec';
                END IF;
                
                days := total_seconds / 86400;
                remaining_seconds := total_seconds - (days * 86400);
                hours_part := remaining_seconds / 3600;
                remaining_seconds := remaining_seconds - (hours_part * 3600);
                minutes_part := remaining_seconds / 60;
                seconds_part := remaining_seconds - (minutes_part * 60);
                
                result_parts := ARRAY[]::TEXT[];
                
                IF days > 0 THEN
                    result_parts := array_append(result_parts, days || 'd');
                END IF;
                IF hours_part > 0 THEN
                    result_parts := array_append(result_parts, hours_part || 'h');
                END IF;
                IF minutes_part > 0 THEN
                    result_parts := array_append(result_parts, minutes_part || 'm');
                END IF;
                IF seconds_part > 0 AND array_length(result_parts, 1) < 2 THEN
                    result_parts := array_append(result_parts, seconds_part || 's');
                END IF;
                
                IF array_length(result_parts, 1) > 0 THEN
                    RETURN array_to_string(result_parts, ' ');
                ELSE
                    RETURN '0 sec';
                END IF;
            END;
            $func$ LANGUAGE plpgsql;
        """)
        
        # Create the view
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW {} AS (
                -- ── Core: one row per (team, contributor) ────────────────────
                -- Denominators use COUNT(DISTINCT ticket_id) so metrics match
                -- the ticket count shown in the grouped list view header.
                SELECT
                    ROW_NUMBER() OVER (ORDER BY team_id, contributor_id) AS id,
                    NULL::INTEGER                        AS ticket_id,
                    NULL::VARCHAR                        AS ticket_name,
                    team_id,
                    total_response_time,
                    tag_count,
                    CASE WHEN tag_count > 0 THEN total_response_time / tag_count ELSE 0 END AS avg_response_time,
                    total_resolution_time,
                    CASE WHEN closed_count > 0 THEN total_resolution_time / closed_count ELSE 0 END AS avg_resolution_time,
                    closed_count,
                    NULL::INTEGER                        AS ticket_stage_id,
                    NULL::INTEGER                        AS ticket_team_id,
                    NULL::INTEGER                        AS partner_id,
                    NULL::INTEGER                        AS user_id,
                    MIN(create_date)                     AS create_date,
                    NULL::VARCHAR                        AS priority,
                    contributor_id,
                    'Tagged'                             AS contributor_type,
                    hold_count,
                    0.0                                  AS total_logged_hours,
                    format_hours_to_desc(total_response_time)  AS total_response_time_desc,
                    format_hours_to_desc(
                        CASE WHEN tag_count > 0 THEN total_response_time / tag_count ELSE 0 END
                    ) AS avg_response_time_desc,
                    format_hours_to_desc(total_resolution_time) AS total_resolution_time_desc,
                    format_hours_to_desc(
                        CASE WHEN closed_count > 0 THEN total_resolution_time / closed_count ELSE 0 END
                    ) AS avg_resolution_time_desc,

                    -- ── Collaboration Score Metrics ──────────────────────────
                    -- Denominator = unique tickets this contributor was tagged on
                    -- PR : tickets where contributor accepted / unique tickets × 100
                    CASE WHEN unique_tickets > 0
                        THEN ROUND((tickets_accepted::NUMERIC / unique_tickets::NUMERIC) * 100, 2)
                        ELSE 0 END AS participation_rate,

                    -- CR : tickets where contributor closed / unique tickets × 100
                    CASE WHEN unique_tickets > 0
                        THEN ROUND((tickets_closed::NUMERIC / unique_tickets::NUMERIC) * 100, 2)
                        ELSE 0 END AS resolution_rate,

                    -- SLA% : tickets responded within SLA / unique tickets × 100
                    CASE WHEN unique_tickets > 0
                        THEN ROUND((tickets_within_sla::NUMERIC / unique_tickets::NUMERIC) * 100, 2)
                        ELSE 0 END AS sla_compliance_rate,

                    -- Rework% : re-tagged tickets (tagged >1 time) / unique tickets × 100
                    CASE WHEN unique_tickets > 0
                        THEN ROUND((rework_tickets::NUMERIC / unique_tickets::NUMERIC) * 100, 2)
                        ELSE 0 END AS rework_rate,

                    -- CTCS = 0.35×PR + 0.35×CR + 0.20×SLA% − 0.10×Rework%
                    CASE WHEN unique_tickets > 0
                        THEN ROUND(
                            0.35 * (tickets_accepted::NUMERIC  / unique_tickets::NUMERIC) * 100
                          + 0.35 * (tickets_closed::NUMERIC    / unique_tickets::NUMERIC) * 100
                          + 0.20 * (tickets_within_sla::NUMERIC / unique_tickets::NUMERIC) * 100
                          - 0.10 * (rework_tickets::NUMERIC    / unique_tickets::NUMERIC) * 100
                        , 2)
                        ELSE 0 END AS collaboration_score,

                    -- Performance Rating text
                    CASE
                        WHEN unique_tickets > 0 AND ROUND(
                            0.35 * (tickets_accepted::NUMERIC  / unique_tickets::NUMERIC) * 100
                          + 0.35 * (tickets_closed::NUMERIC    / unique_tickets::NUMERIC) * 100
                          + 0.20 * (tickets_within_sla::NUMERIC / unique_tickets::NUMERIC) * 100
                          - 0.10 * (rework_tickets::NUMERIC    / unique_tickets::NUMERIC) * 100
                        , 2) >= 90 THEN 'excellent'
                        WHEN unique_tickets > 0 AND ROUND(
                            0.35 * (tickets_accepted::NUMERIC  / unique_tickets::NUMERIC) * 100
                          + 0.35 * (tickets_closed::NUMERIC    / unique_tickets::NUMERIC) * 100
                          + 0.20 * (tickets_within_sla::NUMERIC / unique_tickets::NUMERIC) * 100
                          - 0.10 * (rework_tickets::NUMERIC    / unique_tickets::NUMERIC) * 100
                        , 2) >= 80 THEN 'stable'
                        WHEN unique_tickets > 0 AND ROUND(
                            0.35 * (tickets_accepted::NUMERIC  / unique_tickets::NUMERIC) * 100
                          + 0.35 * (tickets_closed::NUMERIC    / unique_tickets::NUMERIC) * 100
                          + 0.20 * (tickets_within_sla::NUMERIC / unique_tickets::NUMERIC) * 100
                          - 0.10 * (rework_tickets::NUMERIC    / unique_tickets::NUMERIC) * 100
                        , 2) >= 70 THEN 'at_risk'
                        ELSE 'critical'
                    END AS performance_rating,

                    -- Performance Rating numeric: 4=Excellent, 3=Stable, 2=At Risk, 1=Critical
                    CASE
                        WHEN unique_tickets > 0 AND ROUND(
                            0.35 * (tickets_accepted::NUMERIC  / unique_tickets::NUMERIC) * 100
                          + 0.35 * (tickets_closed::NUMERIC    / unique_tickets::NUMERIC) * 100
                          + 0.20 * (tickets_within_sla::NUMERIC / unique_tickets::NUMERIC) * 100
                          - 0.10 * (rework_tickets::NUMERIC    / unique_tickets::NUMERIC) * 100
                        , 2) >= 90 THEN 4
                        WHEN unique_tickets > 0 AND ROUND(
                            0.35 * (tickets_accepted::NUMERIC  / unique_tickets::NUMERIC) * 100
                          + 0.35 * (tickets_closed::NUMERIC    / unique_tickets::NUMERIC) * 100
                          + 0.20 * (tickets_within_sla::NUMERIC / unique_tickets::NUMERIC) * 100
                          - 0.10 * (rework_tickets::NUMERIC    / unique_tickets::NUMERIC) * 100
                        , 2) >= 80 THEN 3
                        WHEN unique_tickets > 0 AND ROUND(
                            0.35 * (tickets_accepted::NUMERIC  / unique_tickets::NUMERIC) * 100
                          + 0.35 * (tickets_closed::NUMERIC    / unique_tickets::NUMERIC) * 100
                          + 0.20 * (tickets_within_sla::NUMERIC / unique_tickets::NUMERIC) * 100
                          - 0.10 * (rework_tickets::NUMERIC    / unique_tickets::NUMERIC) * 100
                        , 2) >= 70 THEN 2
                        ELSE 1
                    END AS performance_rating_num

                FROM (
                    SELECT
                        COALESCE(tag.team_id, t.team_id)           AS team_id,
                        tag.tagged_user_id                          AS contributor_id,
                        MIN(t.create_date)                         AS create_date,

                        -- Volume metrics
                        COUNT(DISTINCT tag.ticket_id)              AS unique_tickets,
                        COUNT(tag.id)                              AS tag_count,
                        COUNT(CASE WHEN tag.action = 'hold' THEN 1 END) AS hold_count,

                        -- Time metrics
                        COALESCE(SUM(tag.response_duration), 0)   AS total_response_time,
                        COALESCE(SUM(tag.resolution_time), 0)     AS total_resolution_time,

                        -- For avg resolution (only closed)
                        COUNT(DISTINCT CASE WHEN tag.closed_at IS NOT NULL
                                            THEN tag.ticket_id END) AS closed_count,

                        -- Collaboration numerators (per unique ticket)
                        COUNT(DISTINCT CASE WHEN tag.accepted_at IS NOT NULL
                                            THEN tag.ticket_id END) AS tickets_accepted,
                        COUNT(DISTINCT CASE WHEN tag.closed_at IS NOT NULL
                                            THEN tag.ticket_id END) AS tickets_closed,
                        COUNT(DISTINCT CASE WHEN t.sla_deadline IS NOT NULL
                                             AND tag.response_time IS NOT NULL
                                             AND tag.response_time <= t.sla_deadline
                                            THEN tag.ticket_id END) AS tickets_within_sla,
                        -- Rework: tickets where this contributor was tagged more than once
                        COUNT(DISTINCT CASE WHEN rework_sub.tag_count > 1
                                            THEN tag.ticket_id END) AS rework_tickets

                    FROM helpdesk_ticket_tag_transfer tag
                    JOIN helpdesk_ticket t ON t.id = tag.ticket_id
                    -- Sub-query to identify re-tagged tickets per contributor
                    LEFT JOIN (
                        SELECT ticket_id, tagged_user_id, COUNT(*) AS tag_count
                        FROM helpdesk_ticket_tag_transfer
                        WHERE tagged_user_id IS NOT NULL
                        GROUP BY ticket_id, tagged_user_id
                    ) rework_sub ON rework_sub.ticket_id = tag.ticket_id
                                AND rework_sub.tagged_user_id = tag.tagged_user_id
                    WHERE tag.tagged_user_id IS NOT NULL
                    GROUP BY COALESCE(tag.team_id, t.team_id), tag.tagged_user_id
                ) base
                -- expose create_date for grouping
                GROUP BY team_id, contributor_id, unique_tickets, tag_count, hold_count,
                         total_response_time, total_resolution_time, closed_count,
                         tickets_accepted, tickets_closed, tickets_within_sla, rework_tickets
            )
        """.format(self._table))
