from odoo import models, fields


class VtsNotificationType(models.Model):
    _name = 'vts.notification.type'
    _description = 'VTS Notification Type'
    _rec_name = 'name'

    key = fields.Char(string='Key', required=True)
    name = fields.Char(string='Name', required=True)


class VtsOperationTeam(models.Model):
    _name = 'vts.operation.team'
    _description = 'VTS Operation Team'

    name = fields.Char(string='Team Name', required=True)
    code = fields.Char(string='Team Code', required=True, unique=True)
    user_id = fields.Many2one('res.users', string='Team Leader', required=True)
    member_ids = fields.Many2many('res.users', string='Team Members')
    notification_type_ids = fields.Many2many(
        'vts.notification.type',
        string='Notification Types',
        help='Notification events this team should receive. '
             'Leave empty to receive no automatic notifications.',
    )