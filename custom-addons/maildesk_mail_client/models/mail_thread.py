# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Mail Thread.

Defines Odoo ORM models and server-side APIs for Mail Thread.
Layer: odoo models.
"""

from odoo import models

from .mail_mail import format_emails


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _maildesk_composer_recipient_from_follower_data(
        self, follower_data: dict
    ) -> dict:
        """
        Build a recipient dict compatible with Odoo's mail notification pipeline.

        Odoo's `mail.thread` notification code expects each recipient entry to
        follow the schema produced by `mail.followers._get_recipient_data()`,
        including keys like `uid` and `ushare`. MailDesk adds CC/BCC recipients
        for composer-originated notifications; this helper ensures those extra
        recipients do not break core assumptions.

        Args:
            follower_data: A recipient dict from `mail.followers._get_recipient_data()`.

        Returns:
            A new recipient dict suitable for `mail.thread._notify_thread_*`
            methods, forcing email notifications for CC/BCC recipients.
        """
        pdata = dict(follower_data or {})

        # Enforce the stable schema expected by Odoo core (avoid KeyError).
        pdata.setdefault("id", False)
        pdata.setdefault("active", False)
        pdata.setdefault("share", False)
        pdata.setdefault("uid", False)
        pdata.setdefault("ushare", False)
        pdata.setdefault("lang", False)
        pdata.setdefault("groups", set())
        pdata.setdefault("is_follower", False)

        # CC/BCC are explicit email recipients; always notify them by email.
        pdata["notif"] = "email"

        # Ensure `type` is consistent when not provided (defensive).
        if not pdata.get("type"):
            if pdata.get("ushare"):
                pdata["type"] = "portal"
            elif pdata.get("share"):
                pdata["type"] = "customer"
            else:
                pdata["type"] = "user"

        return pdata

    def _get_message_create_valid_field_names(self):
        """
        Allows composer-specific fields to flow through message creation.
        Extends the base whitelist so CC/BCC partner links, originating account,
        and folder metadata persist on new chatter messages created from the
        MailDesk composer without being rejected by validation.
        """
        field_names = super()._get_message_create_valid_field_names()
        field_names.update(
            {
                "body_original",
                "account_id",
                "recipient_cc_ids",
                "recipient_bcc_ids",
                "folder_ids",
            }
        )
        return field_names

    def _get_notify_valid_parameters(self):
        """
        Permits additional notification parameters used by the composer in email
        dispatch. By widening the allowed parameter set, the method preserves
        account information and CC/BCC partner hints that would otherwise be
        stripped before notification processing.
        """
        params = set(super()._get_notify_valid_parameters())
        params.update(
            {
                "account_id",
                "recipient_cc_ids",
                "recipient_bcc_ids",
                "folder_ids",
            }
        )
        return params

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        """
        Augments the computed recipient list with explicit CC/BCC partners when
        the notification originates from the composer. It mirrors follower
        classification logic to include these contacts only once and avoids
        duplication by checking recipients already queued for notification.
        """
        msg_vals = msg_vals or {}
        rdata = super()._notify_get_recipients(message, msg_vals=msg_vals, **kwargs)
        context = self.env.context
        if not context.get("is_from_composer") or context.get("skip_cc_bcc"):
            return rdata

        partners_cc_bcc = [
            p.id
            for p in (
                context.get("partner_cc_ids", []) + context.get("partner_bcc_ids", [])
            )
        ]

        recipients_cc_bcc = self.env["mail.followers"]._get_recipient_data(
            None,
            message.message_type,
            msg_vals.get("subtype_id", message.subtype_id.id),
            partners_cc_bcc,
        )

        partners_already_marked_as_recipient = {r.get("id", False) for r in rdata}

        for value in recipients_cc_bcc.values():
            for data in value.values():
                if data.get("id") not in partners_already_marked_as_recipient:
                    pdata = self._maildesk_composer_recipient_from_follower_data(data)
                    if pdata.get("id"):
                        rdata.append(pdata)

        return rdata

    def _notify_get_recipients_classify(
        self, message, recipients_data, model_description, msg_vals=None
    ):
        """
        Collapses recipient buckets so CC and BCC recipients are grouped under
        the "customer" notification channel when sending from the composer.
        Ensures they bypass follower grouping and receive standard customer
        emails alongside existing recipients without generating duplicates.
        """
        res = super()._notify_get_recipients_classify(
            message, recipients_data, model_description, msg_vals=msg_vals
        )
        context = self.env.context
        if not context.get("is_from_composer") or context.get("skip_cc_bcc"):
            return res

        ids = []
        extra_recipients_data = []
        customer_data = None

        for rcpt_data in res:
            if rcpt_data["notification_group_name"] == "customer":
                customer_data = rcpt_data
            else:
                ids += rcpt_data.get("recipients_ids", [])
                extra_recipients_data += rcpt_data.get("recipients_data", [])

        if customer_data:
            customer_data["recipients_ids"].extend(ids)
            customer_data["recipients_data"].extend(extra_recipients_data)
        else:
            customer_data = {
                "notification_group_name": "customer",
                "active": True,
                "has_button_access": False,
                "button_access": {},
                "recipients_ids": ids,
                "recipients_data": extra_recipients_data,
                "recipients_emails": [],
            }

        return [customer_data]

    def _notify_by_email_get_base_mail_values(
        self, message, recipients_data, additional_values=None
    ):
        """
        Injects CC and BCC header strings derived from context into outgoing
        email values when CC/BCC support is enabled. Delegates the rest of the
        payload to the base implementation to preserve standard notification
        formatting.
        """
        res = super()._notify_by_email_get_base_mail_values(
            message, recipients_data, additional_values=additional_values
        )
        context = self.env.context

        if not context.get("skip_cc_bcc"):
            res["email_cc"] = format_emails(context.get("partner_cc_ids", []))
            res["email_bcc"] = format_emails(context.get("partner_bcc_ids", []))

        return res

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        """
        Disables CC/BCC expansion for system-generated notification messages to
        avoid leaking extra recipients, then defers to standard notification
        handling. Regular composer messages are processed unchanged.
        """
        if message.message_type == "notification":
            self = self.with_context(skip_cc_bcc=True)
        return super()._notify_thread(message, msg_vals, **kwargs)

    def _notify_thread_by_email(
        self, message, recipients_data, msg_vals=False, **kwargs
    ):
        """
        Filters out email notifications that have already been generated when a
        skip flag is set, preventing duplicate outbound emails for the same
        partners. After pruning, it delegates to the base email notification
        flow to deliver the remaining messages.
        """
        skip_existing = bool(
            self.env.context.get("maildesk_skip_existing", False)
        ) or bool(kwargs.get("skip_existing"))
        if skip_existing and recipients_data:
            email_partner_ids = [
                r["id"] for r in recipients_data if r.get("notif") == "email"
            ]
            if email_partner_ids:
                existing = (
                    self.env["mail.notification"]
                    .sudo()
                    .search(
                        [
                            ("mail_message_id", "=", message.id),
                            ("notification_type", "=", "email"),
                            ("res_partner_id", "in", email_partner_ids),
                        ]
                    )
                )
                already = set(existing.mapped("res_partner_id").ids)
                recipients_data = [
                    r
                    for r in recipients_data
                    if not (r.get("notif") == "email" and r["id"] in already)
                ]

        return super()._notify_thread_by_email(
            message, recipients_data, msg_vals=msg_vals, **kwargs
        )
