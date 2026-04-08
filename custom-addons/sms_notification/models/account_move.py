import logging
import re
from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    sms_notification_limit = fields.Integer('SMS Notification Limit', default=0)
    new_registration_sms_limit = fields.Integer('SMS Limit New Registration', default=0)
    fifteen_days_sms_limit = fields.Integer('SMS Limit 15 days', default=0)
    due_day_sms_limit = fields.Integer('Due SMS Limit', default=0)
    seven_days_sms_limit = fields.Integer('SMS Limit 7 days', default=0)
    above_seven_days_sms_limit = fields.Integer('SMS Limit Above 7 days', default=0)
    thirty_days_before_sms_limit = fields.Integer('SMS Limit 30 Days Before', default=0)

    car_plate_numbers = fields.Char(string='Car Plate Numbers', compute='_compute_car_plate_numbers')

    @api.depends('line_ids')
    def _compute_car_plate_numbers(self):
        for move in self:
            car_plate_numbers = ', '.join(
                re.search(r'T\d{3}[A-Z]{3}', line.name).group()
                for line in move.line_ids
                if line.name and re.search(r'T\d{3}[A-Z]{3}', line.name)
            )
            move.car_plate_numbers = car_plate_numbers

    def queue_sms_notification(self):
        """Generate SMS mailings via mass_mailing_sms for invoice reminders"""
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
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'draft'),
            ('invoice_line_ids.sale_line_ids.order_id.tag_ids.name', 'ilike', 'ATRAS'),
        ]

        draft_invoices = self.search(domains)
        for rec in draft_invoices:
            try:
                self._process_sms_notification(
                    rec,
                    old_invoice_template,
                    new_registration_template,
                    thirty_days_before_template,
                    fifteen_days_before_template,
                    due_day_template,
                    seven_days_after_template,
                    above_seven_days_after_template,
                )
            except (UserError, ValidationError) as e:
                _logger.warning(
                    "SMS notification skipped for invoice %s (id=%s): %s",
                    rec.display_name, rec.id, e,
                )
            except Exception as e:
                _logger.error(
                    "Unexpected error sending SMS for invoice %s (id=%s): %s",
                    rec.display_name, rec.id, e, exc_info=True,
                )

    def _process_sms_notification(
        self,
        rec,
        old_invoice_template,
        new_registration_template,
        thirty_days_before_template,
        fifteen_days_before_template,
        due_day_template,
        seven_days_after_template,
        above_seven_days_after_template,
    ):
        override = False
        if override:
            message = self._render_template(old_invoice_template, rec.id)
            self.create_sms_mailing(obj=rec, message=message, template=old_invoice_template,
                                    sms_type='Other - Invoice Notification')
            rec.new_registration_sms_limit += 1
            rec.fifteen_days_sms_limit += 1
            rec.due_day_sms_limit += 1
            rec.seven_days_sms_limit += 1
            rec.above_seven_days_sms_limit += 1
            rec.thirty_days_before_sms_limit += 1
        else:
            if (
                self.check_validity(rec.invoice_date, rec.new_registration_sms_limit)
                == "new"
            ):
                message = self._render_template(new_registration_template, rec.id)
                self.create_sms_mailing(
                    obj=rec,
                    message=message,
                    template=new_registration_template,
                    sms_type="New Registration",
                )
                rec.new_registration_sms_limit += 1
            if (
                self.check_validity(rec.invoice_date, rec.thirty_days_before_sms_limit)
                == "30-days-before"
            ):
                message = self._render_template(thirty_days_before_template, rec.id)
                self.create_sms_mailing(
                    obj=rec,
                    message=message,
                    template=thirty_days_before_template,
                    sms_type="30 Days Before Reminder",
                )
                rec.thirty_days_before_sms_limit += 1
            if (
                self.check_validity(rec.invoice_date, rec.fifteen_days_sms_limit)
                == "15-days-before"
            ):
                message = self._render_template(fifteen_days_before_template, rec.id)
                self.create_sms_mailing(
                    obj=rec,
                    message=message,
                    template=fifteen_days_before_template,
                    sms_type="15 Days Before Reminder",
                )
                rec.fifteen_days_sms_limit += 1
            if (
                self.check_validity(rec.invoice_date, rec.due_day_sms_limit)
                == "due-day"
            ):
                message = self._render_template(due_day_template, rec.id)
                self.create_sms_mailing(
                    obj=rec,
                    message=message,
                    template=due_day_template,
                    sms_type="Due Date Reminder",
                )
                rec.due_day_sms_limit += 1
            if (
                self.check_validity(rec.invoice_date, rec.seven_days_sms_limit)
                == "7-days-after"
            ):
                message = self._render_template(seven_days_after_template, rec.id)
                self.create_sms_mailing(
                    obj=rec,
                    message=message,
                    template=seven_days_after_template,
                    sms_type="7 Days After Reminder",
                )
                rec.seven_days_sms_limit += 1
            if (
                self.check_validity(rec.invoice_date, rec.above_seven_days_sms_limit)
                == "above-7-days"
            ):
                message = self._render_template(above_seven_days_after_template, rec.id)
                self.create_sms_mailing(
                    obj=rec,
                    message=message,
                    template=above_seven_days_after_template,
                    sms_type="Above 7 Days After Reminder",
                )
                rec.above_seven_days_sms_limit += 1

    def reset_limits(self):
        domains = [
            ('state', '=', 'draft'),
            ('invoice_line_ids.sale_line_ids.order_id.tag_ids.name', 'ilike', 'ATRAS'),
        ]

        draft_invoices = self.search(domains)
        for rec in draft_invoices:
            rec.new_registration_sms_limit = 0
            rec.fifteen_days_sms_limit = 0
            rec.due_day_sms_limit = 0
            rec.above_seven_days_sms_limit = 0
            print("Limit Removed")

    def create_sms_mailing(self, obj, message, template, sms_type):
        """Create a mailing.mailing record for SMS sending via mass_mailing_sms"""
        # Create mailing.mailing record targeting the partner directly
        vals = {
            'sms_subject': f'{sms_type} - {obj.partner_id.name} - Invoice {obj.display_name}',
            'body_plaintext': message,
            'mailing_type': 'sms',
            'mailing_model_id': self.env['ir.model']._get('res.partner').id,
            'mailing_domain': repr([('id', '=', obj.partner_id.id)]),
            'state': 'draft',
            'sms_allow_unsubscribe': False,
        }

        mailing = self.env['mailing.mailing'].create(vals)

        # Put mailing in queue for sending
        mailing.action_put_in_queue()

        obj.sms_notification_limit = 0
        return mailing

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
        # move = self.browse(res_ids)
        # car_plate_numbers = ', '.join(re.search(r'T\d{3}[A-Z]{3}', line.name).group() for line in move.line_ids if line.name and re.search(r'T\d{3}[A-Z]{3}', line.name))
        # context = {
        #     'car_plate_numbers': car_plate_numbers,
        # }
        message =  self.env['sms.template']._render_template(template.body, template.model,[res_ids])
        key_value = list(message)[0]
        return message[key_value]
