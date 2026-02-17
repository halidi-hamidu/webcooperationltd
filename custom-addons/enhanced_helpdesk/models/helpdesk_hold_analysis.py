from odoo import models, fields, tools


class HelpdeskHoldAnalysis(models.Model):
    _name = 'helpdesk.hold.analysis'
    _description = "Helpdesk Hold Analysis Report"
    _auto = False
    _order = 'hold_date DESC'

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
    
    # Hold Information
    hold_user_id = fields.Many2one('res.users', string='User Who Put on Hold', readonly=True)
    hold_date = fields.Datetime('Hold Date', readonly=True)
    hold_duration_hours = fields.Float('Hold Duration (Hours)', readonly=True, group_operator="avg")
    hold_details = fields.Text('Hold Details', readonly=True)
    hold_reasons_text = fields.Char('Hold Reasons', readonly=True)
    
    # Tagged Team Information
    tagged_team_id = fields.Many2one('helpdesk.team', string='Tagged Team', readonly=True)
    tagged_by_user_id = fields.Many2one('res.users', string='Tagged By', readonly=True)
    date_tagged = fields.Datetime('Date Tagged', readonly=True)
    
    # Status
    is_currently_on_hold = fields.Boolean('Currently on Hold', readonly=True)
    hold_count = fields.Integer('Hold Count', readonly=True, group_operator="sum",
                               help='Number of times this ticket was put on hold')

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ROW_NUMBER() OVER (ORDER BY t.id, tag.held_at DESC) AS id,
                    -- Ticket Information
                    t.id AS ticket_id,
                    t.name AS ticket_name,
                    t.stage_id AS ticket_stage_id,
                    t.team_id AS ticket_team_id,
                    t.partner_id AS partner_id,
                    t.user_id AS assigned_user_id,
                    t.create_date AS create_date,
                    t.priority AS priority,
                    
                    -- Hold Information
                    tag.tagged_user_id AS hold_user_id,
                    tag.held_at AS hold_date,
                    CASE 
                        WHEN tag.held_at IS NOT NULL AND tag.closed_at IS NOT NULL THEN
                            EXTRACT(EPOCH FROM (tag.closed_at - tag.held_at)) / 3600.0
                        WHEN tag.held_at IS NOT NULL AND tag.action = 'hold' THEN
                            EXTRACT(EPOCH FROM (NOW() - tag.held_at)) / 3600.0
                        ELSE 0.0
                    END AS hold_duration_hours,
                    tag.hold_details AS hold_details,
                    COALESCE(tag.hold_details, 'No details provided') AS hold_reasons_text,
                    
                    -- Tagged Team Information
                    tag.team_id AS tagged_team_id,
                    tag.tagged_by_user_id AS tagged_by_user_id,
                    tag.date_tagged AS date_tagged,
                    
                    -- Status
                    CASE WHEN tag.action = 'hold' AND tag.closed_at IS NULL THEN TRUE ELSE FALSE END AS is_currently_on_hold,
                    1 AS hold_count
                    
                FROM helpdesk_ticket t
                JOIN helpdesk_ticket_tag_transfer tag ON tag.ticket_id = t.id
                WHERE tag.action = 'hold' OR tag.held_at IS NOT NULL
            )
        """ % self._table)