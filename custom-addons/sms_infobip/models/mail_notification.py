from odoo import api, fields, models


class MailNotification(models.Model):
    _inherit = 'mail.notification'

    failure_type = fields.Selection(
        selection_add=[
            ('infobip_authentication', 'Authentication Error'),
            ('infobip_sender_missing', 'Missing Sender ID'),
            ('infobip_invalid_number', 'Invalid Number'),
        ],
    )

    # CRUD
    # ------------------------------------------------------------

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        # Ensure translations are loaded for new selection values
        res = super().fields_get(allfields=allfields, attributes=attributes)

        existing_selection = res.get('failure_type', {}).get('selection')
        if existing_selection is None:
            return res

        updated_stable = {
            'infobip_authentication',
            'infobip_sender_missing',
            'infobip_invalid_number',
        }
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
