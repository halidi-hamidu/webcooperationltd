from odoo import fields, models, api
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    atras_project_ids = fields.One2many('project.project', 'sale_order_id', domain=[('business_line', '=', 'atras')])
    registration_sms_limit = fields.Integer('Registration SMS Limit')

    def send_registration_sms(self):
        if self.atras_project_ids:
            new_registration_template = self.env.ref('sms_notification.sms_notification_template_new_registration')
            message = self._render_template(new_registration_template, self.id)
            vals = {
                'customer': self.partner_id.id,
                'message': self.clean_message(message),
                'body_html': new_registration_template.body,
                'state': 'outgoing',
                'type': 'new',
            }
            self.create_sms_record(vals)
            self.registration_sms_limit += 1
        else:
            raise UserError("You have not selected registered Cars")

    def clean_message(self, message):
        message_words = message.split()
        cleaned_message = ' '.join(message_words)
        return cleaned_message

    def create_sms_record(self, vals):
        self.env['sms.notification'].create(vals)

    def update_sms_record(self):
        pass

    def _render_template(self, template, res_ids):
        return self.env['sms.template']._render_template(template.body, template.model, res_ids)
