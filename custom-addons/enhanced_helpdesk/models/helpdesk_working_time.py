from odoo import models, fields, api


class HelpdeskWorkingTime(models.Model):
    _name = 'helpdesk.working.time'
    _description = ' Working Time Configuration for Helpdesk Tickets to Calculate SLA'
    _rec_name = 'name'

    name = fields.Char(string='Configuration Name', required=True, default='Working Time Configuration')
    day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day of Week', required=True)
    hour_from = fields.Float(string='Work from', required=True, default=8.0, 
                            help='Start hour (24-hour format, e.g., 8.0 for 8:00 AM)')
    hour_to = fields.Float(string='Work to', required=True, default=17.0,
                          help='End hour (24-hour format, e.g., 17.0 for 5:00 PM)')
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.constrains('hour_from', 'hour_to')
    def _check_working_hours(self):
        for record in self:
            if record.hour_from >= record.hour_to:
                raise models.ValidationError('Work start time must be before work end time.')
            if record.hour_from < 0 or record.hour_from > 24:
                raise models.ValidationError('Work start time must be between 0 and 24.')
            if record.hour_to < 0 or record.hour_to > 24:
                raise models.ValidationError('Work end time must be between 0 and 24.')

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} - {dict(record._fields['day_of_week'].selection)[record.day_of_week]}"
            result.append((record.id, name))
        return result
