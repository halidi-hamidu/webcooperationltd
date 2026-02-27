from odoo import models, fields, api


class HelpdeskTagCategory(models.Model):
    _name = 'helpdesk.tag.category'
    _description = 'Helpdesk Tag Category'
    _order = 'team_id, name'

    name = fields.Char(string='Category Name', required=True)
    team_id = fields.Many2one(
        'helpdesk.team',
        string='Team',
        required=True,
        ondelete='cascade',
        help='This tag category belongs to this helpdesk team',
    )
    sla_ids = fields.One2many(
        'helpdesk.sla',
        'tag_category_id',
        string='SLA Policies',
        help='SLA Policies that reference this tag category',
    )
    tag_ids = fields.One2many(
        'helpdesk.tag',
        'tag_category_id',
        string='Tags',
        help='Tags that belong to this category',
    )
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description')

    _sql_constraints = [
        ('name_team_uniq', 'unique(name, team_id)',
         'A tag category with this name already exists for this team.'),
    ]
