from odoo import models, fields, api


class HelpdeskTag(models.Model):
    _inherit = 'helpdesk.tag'

    team_id = fields.Many2one(
        'helpdesk.team',
        string='Team',
        help='Restrict this tag to a specific helpdesk team',
        ondelete='set null',
    )
    tag_category_id = fields.Many2one(
        'helpdesk.tag.category',
        string='Tag Category',
        help='Category this tag belongs to',
        ondelete='set null',
    )
