from odoo import models, fields

INFOBIP_STATUS_TO_FAILURE_TYPE = {
    # Map Infobip status to Odoo failure types
    'REJECTED': 'rejected',
    'UNDELIVERABLE': 'invalid_destination',
    'EXPIRED': 'expired',
    'NOT_SENT': 'not_delivered',
    'DELIVERY_IMPOSSIBLE': 'invalid_destination',
}


class SmsTracker(models.Model):
    _inherit = 'sms.tracker'

    sms_infobip_message_id = fields.Char(
        string='Infobip Message ID',
        readonly=True,
        help='Message ID returned by Infobip API'
    )

    def _action_update_from_infobip_error(self, sms_status, error_message=None):
        """Update the SMS tracker with the Infobip status and error message"""
        failure_type = INFOBIP_STATUS_TO_FAILURE_TYPE.get(
            sms_status,
            None if sms_status == "FAILED" else "not_delivered"
        )
        context = {}
        if error_message:
            context = {'sms_known_failure_reason': error_message}
        return self.with_context(**context)._action_update_from_provider_error(failure_type)
