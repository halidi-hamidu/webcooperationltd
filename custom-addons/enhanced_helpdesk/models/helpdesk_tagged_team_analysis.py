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
        group_operator="sum",
        readonly=True,
        help='Sum of all response times for tagged users in this team'
    )
    tag_count = fields.Integer(
        string='Number of Tags',
        group_operator="sum",
        readonly=True,
        help='Number of times users from this team were tagged'
    )
    avg_response_time = fields.Float(
        string='Average Response Time (Hours)',
        group_operator="avg",
        readonly=True,
        help='Average response time per tag for this team'
    )
    ticket_stage_id = fields.Many2one('helpdesk.stage', string='Ticket Stage', readonly=True)
    ticket_team_id = fields.Many2one('helpdesk.team', string='Ticket Team', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    user_id = fields.Many2one('res.users', string='Assigned To', readonly=True)
    create_date = fields.Datetime("Created On", readonly=True)
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Medium'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], string='Priority', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    ROW_NUMBER() OVER (ORDER BY t.id, team.id) AS id,
                    t.id AS ticket_id,
                    t.name AS ticket_name,
                    team.id AS team_id,
                    SUM(COALESCE(tag.response_duration, 0)) AS total_response_time,
                    COUNT(tag.id) AS tag_count,
                    AVG(COALESCE(tag.response_duration, 0)) AS avg_response_time,
                    t.stage_id AS ticket_stage_id,
                    t.team_id AS ticket_team_id,
                    t.partner_id AS partner_id,
                    t.user_id AS user_id,
                    t.create_date AS create_date,
                    t.priority AS priority
                FROM 
                    helpdesk_ticket t
                LEFT JOIN 
                    helpdesk_ticket_tag_transfer tag ON tag.ticket_id = t.id
                LEFT JOIN 
                    helpdesk_team team ON team.id = tag.team_id
                WHERE 
                    tag.team_id IS NOT NULL
                GROUP BY 
                    t.id, t.name, team.id, t.stage_id, t.team_id, 
                    t.partner_id, t.user_id, t.create_date, t.priority
            )
        """ % self._table)
