from collections import defaultdict

from odoo import fields, models, api


class SmsSms(models.Model):
    _inherit = 'sms.sms'

    sms_infobip_message_id = fields.Char(
        related="sms_tracker_id.sms_infobip_message_id",
        depends=['sms_tracker_id'],
        string='Infobip Message ID'
    )
    record_company_id = fields.Many2one('res.company', 'Company', ondelete='set null')
    failure_type = fields.Selection(
        selection_add=[
            ('infobip_authentication', 'Authentication Error'),
            ('infobip_sender_missing', 'Missing Sender ID'),
            ('infobip_invalid_number', 'Invalid Number'),
        ],
    )

    # CRUD
    # ------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['record_company_id'] = vals.get('record_company_id') or self.env.company.id
        return super().create(vals_list)

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        # Ensure translations are loaded for new selection values
        res = super().fields_get(allfields=allfields, attributes=attributes)

        existing_selection = res.get('failure_type', {}).get('selection')
        if existing_selection is None:
            return res

        updated_stable = {'infobip_sender_missing', 'infobip_invalid_number'}
        need_update = updated_stable - set(dict(self._fields['failure_type'].selection))
        if need_update:
            self.env['ir.model.fields'].invalidate_model(['selection_ids'])
            self.env['ir.model.fields.selection']._update_selection(
                self._name,
                'failure_type',
                self._fields['failure_type'].selection,
            )
            self.env.registry.clear_cache()
            return super().fields_get(allfields=allfields, attributes=attributes)

        return res

    # SEND
    # ------------------------------------------------------------

    def _split_by_api(self):
        # Override to handle Infobip or IAP choice, which is company dependent
        sms_by_company = defaultdict(lambda: self.env['sms.sms'])
        todo_via_super = self.browse()
        for sms in self:
            sms_by_company[sms._get_sms_company()] += sms
        for company, company_sms in sms_by_company.items():
            if company.sms_provider == "infobip":
                sms_api = company._get_sms_api_class()(self.env)
                sms_api._set_company(company)
                yield sms_api, company_sms
            else:
                todo_via_super += company_sms
        if todo_via_super:
            yield from super(SmsSms, todo_via_super)._split_by_api()

    def _get_sms_company(self):
        return self.mail_message_id.record_company_id or self.record_company_id or super()._get_sms_company()

    def _get_send_batch_size(self):
        companies = self._get_sms_company()
        if companies and any(company.sms_provider == 'infobip' for company in companies):
            return int(self.env['ir.config_parameter'].sudo().get_param('sms_infobip.session.batch.size', 10))
        return super()._get_send_batch_size()

    def _handle_call_result_hook(self, results):
        """
        Store the message_id of Infobip on the SMS tracking record (as SMS will be deleted)
        :param results: a list of dict in the form [{
            'uuid': Odoo's id of the SMS,
            'state': State of the SMS in Odoo,
            'sms_infobip_message_id': Infobip's message ID,
        }, ...]
        """
        infobip_sms = self.filtered(lambda s: s._get_sms_company().sms_provider == 'infobip')
        grouped_infobip_sms = infobip_sms.grouped("uuid")
        for result in results:
            sms = grouped_infobip_sms.get(result.get('uuid'))
            if sms and sms.sms_tracker_id and result.get('sms_infobip_message_id'):
                sms.sms_tracker_id.sms_infobip_message_id = result['sms_infobip_message_id']
        super(SmsSms, self - infobip_sms)._handle_call_result_hook(results)
