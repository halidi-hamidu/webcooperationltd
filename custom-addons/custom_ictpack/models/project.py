# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, exceptions, fields, models, _
from datetime import date, datetime
import pytz

class Project(models.Model):
    _inherit = 'project.project'

    business_line = fields.Selection([
        ('atras', 'IoT VTS'),
        ('ects', 'IoT ECTS'),
        ('itms', 'IT Management & Security Services'),
        ('uis', 'Unified Infrastructure Solutions'),
        ('ictpack', 'Application Software'),
    ], string='Business Line', default='atras',index=True, readonly=False, required=True, copy=False)


class Task(models.Model):
    _inherit = "project.task"

    state = fields.Selection([
        ('overdue', 'Overdue'),
        ('today', 'Today'),
        ('planned', 'Planned')], 'State',
        default='planned')
    
    def _compute_status(self):
        records = self.env['project.task'].search([])
        for record in records:
            tz = record.user_id.sudo().tz
            date_deadline = record.date_deadline
            date_deadline = fields.Date.from_string(date_deadline)
            today_default = date.today()
            today = today_default
            if tz:
                today_utc = pytz.UTC.localize(datetime.utcnow())
                today_tz = today_utc.astimezone(pytz.timezone(tz))
                today = date(year=today_tz.year, month=today_tz.month, day=today_tz.day)
            if date_deadline:
                diff = (date_deadline - today)
            else:
                diff = (today - today)

            if diff.days == 0:
                record.state = 'today'
            elif diff.days < 0:
                record.state = 'overdue'
            else:
                record.state = 'planned'