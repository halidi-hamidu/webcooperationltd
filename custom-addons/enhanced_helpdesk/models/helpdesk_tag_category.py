from odoo import models, fields, api


class HelpdeskTagCategory(models.Model):
    _name = 'helpdesk.tag.category'
    _description = 'Helpdesk Tag Category'
    _order = 'name'

    name = fields.Char(string='Category Name', required=True)
    team_id = fields.Many2one(
        'helpdesk.team',
        string='Team',
        required=False,
        ondelete='set null',
        help='This tag category belongs to this helpdesk team (optional)',
    )
    sla_ids = fields.One2many(
        'helpdesk.sla',
        'tag_category_id',
        string='SLA Policies',
        help='SLA Policies that reference this tag category',
    )
    # Many2many: a category can contain many tags and a tag can belong
    # to many categories. Use the same relation table as defined on
    # the tag side ('helpdesk_tag_category_rel').
    tag_ids = fields.Many2many(
        'helpdesk.tag',
        'helpdesk_tag_category_rel',
        'category_id',
        'tag_id',
        string='Tags',
        help='Tags that belong to this category',
    )
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')

    # When team_id is optional we enforce uniqueness on name only
    _name_uniq = models.Constraint('unique(name)', 'A tag category with this name already exists.')
