# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMailThreadCcBccRecipientsSchema(TransactionCase):
    """Ensure MailDesk CC/BCC recipients comply with Odoo notify schema."""

    def test_cc_bcc_recipients_include_ushare_key(self):
        record = self.env["res.partner"].create({"name": "MailDesk Thread Target"})
        msg = self.env["mail.message"].create(
            {
                "model": "res.partner",
                "res_id": record.id,
                "body": "<p>test</p>",
                "message_type": "comment",
                "subtype_id": self.env.ref("mail.mt_comment").id,
            }
        )

        bcc_partner = self.env["res.partner"].create({"name": "MailDesk BCC Partner"})
        msg_vals = {
            "partner_ids": [],
            "message_type": "comment",
            "subtype_id": msg.subtype_id.id,
        }

        recipients = record.with_context(
            is_from_composer=True,
            partner_cc_ids=self.env.user.partner_id,
            partner_bcc_ids=bcc_partner,
        )._notify_get_recipients(msg, msg_vals)

        self.assertTrue(recipients)
        for r in recipients:
            # This expression mirrors the one that crashed in customer logs and must never raise.
            _ = bool(r["id"] and r["uid"] and not r["ushare"])
