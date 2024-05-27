# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, exceptions, fields, models, _
from datetime import date, datetime
import pytz

class MailActivity(models.Model):
    _inherit = 'mail.activity'

    status = fields.Selection([
        ('overdue', 'Overdue'),
        ('today', 'Today'),
        ('planned', 'Planned')], 'Status',
        default='planned')
    

    def _compute_status(self):
        records = self.env['mail.activity'].search([])
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
            diff = (date_deadline - today)
            if diff.days == 0:
                record.status = 'today'
            elif diff.days < 0:
                record.status = 'overdue'
            else:
                record.status = 'planned'