from odoo import models, fields, tools


class HelpdeskHoldStatusCountAnalysis(models.Model):
    _name = 'helpdesk.hold.status.count.analysis'
    _description = 'On Hold Status Count Analysis'
    _auto = False
    _order = 'usage_count desc'

    # Hold Reason Information
    hold_reason_id = fields.Many2one('helpdesk.hold.reason', string='Hold Reason', readonly=True)
    reason_name = fields.Char('Reason Name', readonly=True)
    reason_description = fields.Text('Reason Description', readonly=True)
    
    # Count Statistics
    usage_count = fields.Integer('Count', readonly=True, group_operator="sum",
                                help='Number of times this hold reason was used')
    
    # Time Statistics
    avg_hold_duration = fields.Float('Avg Hold Duration (Hours)', readonly=True, group_operator="avg")
    total_hold_duration = fields.Float('Total Hold Duration (Hours)', readonly=True, group_operator="sum")
    
    # Date Information
    last_used_date = fields.Datetime('Last Used', readonly=True)
    first_used_date = fields.Datetime('First Used', readonly=True)
    
    # Additional Statistics
    unique_tickets_count = fields.Integer('Unique Tickets', readonly=True,
                                        help='Number of unique tickets that used this hold reason')
    unique_users_count = fields.Integer('Unique Users', readonly=True,
                                       help='Number of unique users who used this hold reason')
    
    # Status
    is_active = fields.Boolean('Active', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH hold_reason_usage AS (
                    SELECT
                        hr.id as hold_reason_id,
                        hr.name as reason_name,
                        hr.description as reason_description,
                        hr.active as is_active,
                        COUNT(DISTINCT rel.helpdesk_ticket_tag_transfer_id) FILTER (
                            WHERE tag.action = 'hold' 
                            AND tag.held_at IS NOT NULL
                        ) as usage_count,
                        AVG(CASE 
                            WHEN tag.held_at IS NOT NULL AND tag.closed_at IS NOT NULL THEN
                                EXTRACT(EPOCH FROM (tag.closed_at - tag.held_at)) / 3600.0
                            WHEN tag.held_at IS NOT NULL AND tag.action = 'hold' THEN
                                EXTRACT(EPOCH FROM (NOW() - tag.held_at)) / 3600.0
                            ELSE NULL
                        END) as avg_hold_duration,
                        SUM(CASE 
                            WHEN tag.held_at IS NOT NULL AND tag.closed_at IS NOT NULL THEN
                                EXTRACT(EPOCH FROM (tag.closed_at - tag.held_at)) / 3600.0
                            WHEN tag.held_at IS NOT NULL AND tag.action = 'hold' THEN
                                EXTRACT(EPOCH FROM (NOW() - tag.held_at)) / 3600.0
                            ELSE 0
                        END) as total_hold_duration,
                        MAX(CASE 
                            WHEN tag.action = 'hold' THEN tag.held_at 
                            ELSE NULL 
                        END) as last_used_date,
                        MIN(CASE 
                            WHEN tag.action = 'hold' THEN tag.held_at 
                            ELSE NULL 
                        END) as first_used_date,
                        COUNT(DISTINCT CASE 
                            WHEN tag.action = 'hold' THEN tag.ticket_id 
                            ELSE NULL 
                        END) as unique_tickets_count,
                        COUNT(DISTINCT CASE 
                            WHEN tag.action = 'hold' THEN tag.tagged_user_id 
                            ELSE NULL 
                        END) as unique_users_count
                    FROM helpdesk_hold_reason hr
                    LEFT JOIN helpdesk_hold_reason_helpdesk_ticket_tag_transfer_rel rel 
                        ON hr.id = rel.helpdesk_hold_reason_id
                    LEFT JOIN helpdesk_ticket_tag_transfer tag 
                        ON rel.helpdesk_ticket_tag_transfer_id = tag.id
                    GROUP BY hr.id, hr.name, hr.description, hr.active
                )
                SELECT
                    hold_reason_id as id,
                    hold_reason_id,
                    reason_name,
                    reason_description,
                    COALESCE(usage_count, 0) as usage_count,
                    COALESCE(avg_hold_duration, 0) as avg_hold_duration,
                    COALESCE(total_hold_duration, 0) as total_hold_duration,
                    last_used_date,
                    first_used_date,
                    COALESCE(unique_tickets_count, 0) as unique_tickets_count,
                    COALESCE(unique_users_count, 0) as unique_users_count,
                    is_active
                FROM hold_reason_usage
                ORDER BY usage_count DESC, reason_name
            )
        """ % self._table) 