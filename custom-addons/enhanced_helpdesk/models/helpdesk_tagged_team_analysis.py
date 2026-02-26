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
                -- Only contributions from tag transfers (tagged users) for clarity
                SELECT
                    ROW_NUMBER() OVER (ORDER BY t.id, COALESCE(tag.team_id, t.team_id), tag.tagged_user_id) AS id,
                    t.id AS ticket_id,
                    t.name AS ticket_name,
                    COALESCE(tag.team_id, t.team_id) AS team_id,
                    COALESCE(SUM(tag.response_duration), 0) AS total_response_time,
                    COALESCE(COUNT(tag.id), 0) AS tag_count,
                    CASE WHEN COUNT(tag.id) > 0 THEN AVG(tag.response_duration) ELSE 0 END AS avg_response_time,
                    COALESCE(SUM(tag.resolution_time), 0) AS total_resolution_time,
                    CASE WHEN COUNT(CASE WHEN tag.closed_at IS NOT NULL THEN 1 END) > 0 
                         THEN AVG(CASE WHEN tag.closed_at IS NOT NULL THEN tag.resolution_time END)
                         ELSE 0 END AS avg_resolution_time,
                    COALESCE(COUNT(CASE WHEN tag.closed_at IS NOT NULL THEN 1 END), 0) AS closed_count,
                    t.stage_id AS ticket_stage_id,
                    t.team_id AS ticket_team_id,
                    t.partner_id AS partner_id,
                    t.user_id AS user_id,
                    t.create_date AS create_date,
                    t.priority AS priority,
                    tag.tagged_user_id AS contributor_id,
                    'Tagged' AS contributor_type,
                    COUNT(CASE WHEN tag.action = 'hold' THEN 1 END) AS hold_count,
                    0.0 AS total_logged_hours,
                    format_hours_to_desc(COALESCE(SUM(tag.response_duration), 0)) AS total_response_time_desc,
                    format_hours_to_desc(CASE WHEN COUNT(tag.id) > 0 THEN AVG(tag.response_duration) ELSE 0 END) AS avg_response_time_desc,
                    format_hours_to_desc(COALESCE(SUM(tag.resolution_time), 0)) AS total_resolution_time_desc,
                    format_hours_to_desc(CASE WHEN COUNT(CASE WHEN tag.closed_at IS NOT NULL THEN 1 END) > 0 
                                               THEN AVG(CASE WHEN tag.closed_at IS NOT NULL THEN tag.resolution_time END)
                                               ELSE 0 END) AS avg_resolution_time_desc
                FROM helpdesk_ticket t
                JOIN helpdesk_ticket_tag_transfer tag ON tag.ticket_id = t.id
                WHERE tag.tagged_user_id IS NOT NULL
                GROUP BY t.id, t.name, t.stage_id, t.team_id, t.partner_id, t.user_id, 
                         t.create_date, t.priority, tag.tagged_user_id, tag.team_id
            )
        """.format(self._table))
