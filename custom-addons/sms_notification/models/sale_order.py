from odoo import fields, models, api
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    atras_project_ids = fields.One2many('project.project', 'sale_order_id', domain=[('business_line', '=', 'atras')])
    registration_sms_limit = fields.Integer('Registration SMS Limit')

    def send_registration_sms(self):
        """Generate SMS mailing via mass_mailing_sms for new registration"""
        if self.atras_project_ids:
            new_registration_template = self.env.ref('sms_notification.sms_notification_template_new_registration')
            message = self._render_template(new_registration_template, self.id)
            self.create_sms_mailing(message)
            self.registration_sms_limit += 1
        else:
            raise UserError("You have not selected registered Cars")

    def clean_message(self, message):
        """Clean message text by removing extra whitespace"""
        message_words = message.split()
        cleaned_message = ' '.join(message_words)
        return cleaned_message

    def create_sms_mailing(self, message):
        """Create a mailing.mailing record for SMS sending via mass_mailing_sms"""
        # Create mailing.mailing record targeting the partner directly
        vals = {
            'sms_subject': f'New Registration - {self.partner_id.name} - SO {self.name}',
            'body_plaintext': self.clean_message(message),
            'mailing_type': 'sms',
            'mailing_model_id': self.env['ir.model']._get('res.partner').id,
            'mailing_domain': repr([('id', '=', self.partner_id.id)]),
            'state': 'draft',
            'sms_allow_unsubscribe': False,
        }
        
        mailing = self.env['mailing.mailing'].create(vals)
        mailing.action_put_in_queue()
        
        return mailing

    def _render_template(self, template, res_ids):
        """Render SMS template"""
        message = self.env['sms.template']._render_template(template.body, template.model, [res_ids])
        key_value = list(message)[0]
        return message[key_value]
