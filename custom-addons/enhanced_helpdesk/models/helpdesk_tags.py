from odoo import models, fields, api


class HelpdeskTag(models.Model):
    _inherit = 'helpdesk.tag'

    team_id = fields.Many2one(
        'helpdesk.team',
        string='Team',
        help='Restrict this tag to a specific helpdesk team',
        ondelete='set null',
    )
    # A tag can belong to multiple categories and a category can contain
    # multiple tags — use a Many2many relation. We define an explicit
    # relation table so both sides reference the same relation.
    tag_category_ids = fields.Many2many(
        'helpdesk.tag.category',
        'helpdesk_tag_category_rel',
        'tag_id',
        'category_id',
        string='Tag Categories',
        help='Categories this tag belongs to',
    )
