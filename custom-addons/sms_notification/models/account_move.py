from odoo import fields, models, api
from datetime import timedelta


class AccountMove(models.Model):
    _inherit = 'account.move'

    sms_notification_limit = fields.Integer('SMS Notification Limit', default=0)
    new_registration_sms_limit = fields.Integer('SMS Limit New Registration', default=0)
    fifteen_days_sms_limit = fields.Integer('SMS Limit 15 days', default=0)
    due_day_sms_limit = fields.Integer('Due SMS Limit', default=0)
    seven_days_sms_limit = fields.Integer('SMS Limit 7 days', default=0)
    above_seven_days_sms_limit = fields.Integer('SMS Limit Above 7 days', default=0)
    thirty_days_before_sms_limit = fields.Integer('SMS Limit 30 Days Before', default=0)

    def queue_sms_notification(self):
        old_invoice_template = self.env.ref('sms_notification.sms_notification_template_old_invoice_template')
        new_registration_template = self.env.ref('sms_notification.sms_notification_template_new_registration')
        thirty_days_before_template = self.env.ref(
            'sms_notification.sms_notification_template_30_days_before_reminder')
        fifteen_days_before_template = self.env.ref(
            'sms_notification.sms_notification_template_15_days_before_reminder')
        due_day_template = self.env.ref('sms_notification.sms_notification_template_on_due_day')
        seven_days_after_template = self.env.ref('sms_notification.sms_notification_template_7_days_after_reminder')
        above_seven_days_after_template = self.env.ref(
            'sms_notification.sms_notification_template_above_7_days_after_due_day_reminder')

        domains = [
            ('business_line', '=', 'atras'),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'draft'),
        ]

        draft_invoices = self.search(domains)
        for rec in draft_invoices:
            override = False
            if override:
                message = self._render_template(old_invoice_template, rec.id)
                self.create_sms_record(obj=rec, message=message, template=old_invoice_template, type='other')
                rec.new_registration_sms_limit += 1
                rec.fifteen_days_sms_limit += 1
                rec.due_day_sms_limit += 1
                rec.seven_days_sms_limit += 1
                rec.above_seven_days_sms_limit += 1
                rec.thirty_days_before_sms_limit += 1

            else:
                if rec.invoice_date == rec.invoice_date_due:
                    rec.invoice_date_due = rec.invoice_date_due + timedelta(days=30)

                if self.check_validity(rec.invoice_date, rec.new_registration_sms_limit) == 'new':
                    message = self._render_template(new_registration_template, rec.id)
                    self.create_sms_record(obj=rec, message=message, template=new_registration_template, type='new')
                    rec.new_registration_sms_limit += 1
                if self.check_validity(rec.invoice_date, rec.thirty_days_before_sms_limit) == '30-days-before':
                    message = self._render_template(thirty_days_before_template, rec.id)
                    self.create_sms_record(obj=rec, message=message, template=thirty_days_before_template,
                                           type='30days')
                    rec.thirty_days_before_sms_limit += 1
                if self.check_validity(rec.invoice_date, rec.fifteen_days_sms_limit) == '15-days-before':
                    message = self._render_template(fifteen_days_before_template, rec.id)
                    self.create_sms_record(obj=rec, message=message, template=fifteen_days_before_template,
                                           type='15days')
                    rec.fifteen_days_sms_limit += 1
                if self.check_validity(rec.invoice_date, rec.due_day_sms_limit) == 'due-day':
                    message = self._render_template(due_day_template, rec.id)
                    self.create_sms_record(obj=rec, message=message, template=due_day_template, type='due')
                    rec.due_day_sms_limit += 1
                if self.check_validity(rec.invoice_date, rec.seven_days_sms_limit) == '7-days-after':
                    message = self._render_template(seven_days_after_template, rec.id)
                    self.create_sms_record(obj=rec, message=message, template=seven_days_after_template, type='7days')
                    rec.seven_days_sms_limit += 1
                if self.check_validity(rec.invoice_date, rec.above_seven_days_sms_limit) == 'above-7-days':
                    message = self._render_template(above_seven_days_after_template, rec.id)
                    self.create_sms_record(obj=rec, message=message, template=above_seven_days_after_template,
                                           type='above7')
                    rec.above_seven_days_sms_limit += 1

    def reset_limits(self):
        domains = [
            ('business_line', '=', 'atras'),
            ('state', '=', 'draft')
        ]

        draft_invoices = self.search(domains)
        for rec in draft_invoices:
            rec.new_registration_sms_limit = 0
            rec.fifteen_days_sms_limit = 0
            rec.due_day_sms_limit = 0
            rec.above_seven_days_sms_limit = 0
            print("Limit Removed")

    def create_sms_record(self, obj, message, template, type):
        vals = {
            'customer': obj.partner_id.id,
            'message': message,
            'body_html': template.body,
            'state': 'outgoing',
            'type': type,
            'invoice_id': obj.id,
        }
        self.env['sms.notification'].create(vals)
        obj.sms_notification_limit = 0

    def update_sms_record(self):
        pass

    def check_validity(self, invoice_date, sms_limit):
        today = fields.Date.today()
        if invoice_date:
            invoice_date = invoice_date + timedelta(days=30)

            if 15 < (invoice_date - today).days <= 30 and sms_limit == 0 or False:
                return '30-days-before'

            if 15 >= (invoice_date - today).days > 0 == sms_limit or False:
                return '15-days-before'

            if -7 < (invoice_date - today).days <= 0 and sms_limit == 0 or False:
                return 'due-day'

            if -15 < (invoice_date - today).days <= -7 and sms_limit == 0 or False:
                return '7-days-after'

            if (invoice_date - today).days <= -15 and sms_limit == 0 or False:
                return 'above-7-days'

    def _render_template(self, template, res_ids):
        message =  self.env['sms.template']._render_template(template.body, template.model,[res_ids])
        key_value = list(message)[0]
        return message[key_value]
