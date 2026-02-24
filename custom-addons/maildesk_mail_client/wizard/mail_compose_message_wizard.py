# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Mail Compose Message Wizard.

Defines transient wizard models and actions for Mail Compose Message Wizard.
Layer: odoo wizards.
"""

import html
import re

from odoo import api, fields, models


class MailComposeMessage(models.TransientModel):
    _inherit = "mail.compose.message"

    account_id = fields.Many2one(
        "mailbox.account",
        string="Mail Account",
        help="Choose the mail account to send the email from",
    )

    partner_cc_ids = fields.Many2many(
        "res.partner",
        "mail_compose_message_res_partner_cc_rel",
        "wizard_id",
        "partner_id",
        string="Cc",
        help="Contacts to receive a copy of this email (Carbon Copy).",
    )

    partner_bcc_ids = fields.Many2many(
        "res.partner",
        "mail_compose_message_res_partner_bcc_rel",
        "wizard_id",
        "partner_id",
        string="Bcc",
        help="Contacts to receive a blind copy of this email (Blind Carbon Copy). Other recipients will not see these names.",
    )

    custom_from_name = fields.Char(
        string="From Name",
        default=lambda self: self.env.user.name,
        help="Enter the name from which the email will be sent. If empty, default is the user's name.",
    )

    def _prepare_mail_values_rendered(self, res_ids):
        """
        Extends rendered mail values with MailDesk-specific metadata such as
        CC/BCC partner links, reply-to address, and selected mailbox account.
        Iterates over the prepared messages to keep downstream mail creation in
        sync with the wizard selections.
        """
        mail_values = super()._prepare_mail_values_rendered(res_ids)
        for res_id in mail_values:
            mail_values[res_id].update(
                {
                    "recipient_cc_ids": self.partner_cc_ids.ids,
                    "recipient_bcc_ids": self.partner_bcc_ids.ids,
                    "reply_to": self.reply_to,
                    "account_id": (self.account_id.id if self.account_id else False),
                }
            )
        return mail_values

    def _action_send_mail_comment(self, res_ids):
        """
        Sends comment emails with context flags indicating composer origin,
        selected account, and CC/BCC partners so mail thread logic can honor
        those choices. Delegates to the base send logic after enriching the
        environment to ensure proper authorship and routing.
        """
        self = self.with_context(
            is_from_composer=True,
            force_current_user_as_author=True,
            mailbox_is_read=True,
            mailbox_account_id=(self.account_id.id if self.account_id else False),
            partner_cc_ids=self.partner_cc_ids,
            partner_bcc_ids=self.partner_bcc_ids,
            mailbox_is_outgoing=True,
        )
        return super()._action_send_mail_comment(res_ids)

    @api.depends("template_id", "account_id")
    def _compute_mail_server_id(self):
        """
        Picks the outgoing mail server preferring the chosen mailbox account and
        falling back to the template's server. Clears the field when neither is
        available to avoid mismatched SMTP routing.
        """
        for composer in self:
            if composer.account_id and composer.account_id.mail_send_server_id:
                composer.mail_server_id = composer.account_id.mail_send_server_id
            elif composer.template_id and composer.template_id.mail_server_id:
                composer.mail_server_id = composer.template_id.mail_server_id
            else:
                composer.mail_server_id = False

    @api.depends(
        "composition_mode",
        "model",
        "res_domain",
        "res_ids",
        "template_id",
        "account_id",
        "custom_from_name",
    )
    def _compute_reply_to(self):
        """
        Derives the reply-to header based on the selected account and custom
        from name, defaulting to template or blank values when absent. Ensures
        replies are directed to the appropriate mailbox instead of the user's
        personal address.
        """
        for composer in self:
            if composer.account_id and composer.custom_from_name:
                composer.reply_to = (
                    f'"{composer.custom_from_name}" <{composer.account_id.email}>'
                )
            elif composer.account_id:
                composer.reply_to = composer.account_id.email
            elif composer.template_id:
                composer._set_value_from_template("reply_to")
            else:
                composer.reply_to = False

    @api.depends(
        "composition_mode",
        "email_from",
        "model",
        "res_domain",
        "res_ids",
        "template_id",
        "account_id",
        "custom_from_name",
    )
    def _compute_authorship(self):
        """
        Determines the From header and author partner for composed messages,
        prioritizing a custom display name and mailbox account address. Falls
        back to template or user defaults, recomputes author partner using mail
        thread utilities when rendering as a comment, and ensures authorship is
        consistent when templates are not rendered.
        """
        Thread = self.env["mail.thread"].with_context(active_test=False)
        for composer in self:
            rendering_mode = (
                composer.composition_mode == "comment"
                and not composer.composition_batch
            )
            updated_author_id = None

            if (
                composer.custom_from_name
                and composer.account_id
                and composer.account_id.email
            ):
                composer.email_from = f'"{composer.custom_from_name}" <{composer.account_id.email if composer.account_id else self.env.user.email_formatted}>'
            elif composer.account_id and composer.account_id.email:
                composer.email_from = (
                    composer.account_id.sender_name or composer.account_id.name
                )
            elif composer.template_id and composer.template_id.email_from:
                composer._set_value_from_template("email_from")
            elif composer.template_id:
                composer.email_from = self.env.user.email_formatted
            elif not composer.template_id or not composer.email_from:
                composer.email_from = self.env.user.email_formatted
                updated_author_id = self.env.user.partner_id.id

            if composer.email_from and rendering_mode and not updated_author_id:
                updated_author_id, _ = Thread._message_compute_author(
                    None,
                    composer.email_from,
                )
                if not updated_author_id:
                    updated_author_id = self.env.user.partner_id.id
            if not rendering_mode or not composer.template_id:
                updated_author_id = self.env.user.partner_id.id

            if updated_author_id:
                composer.author_id = updated_author_id

    def _is_html_effectively_empty(self, html_text):
        """
        Detects whether an HTML string is visually empty by stripping common
        container tags and whitespace entities. Helps decide when to insert
        signatures without leaving stray formatting wrappers.
        """
        if not html_text:
            return True
        text = re.sub(r"<(br|p|div|span)[^>]*>", " ", html_text or "", flags=re.I)
        text = re.sub(r"&nbsp;|\s+", " ", text, flags=re.I).strip()
        return not text

    def _remove_html_garbage_block(self, body_html):
        """
        Strips garbled blocks typically injected by certain composers, focusing
        on escaped div fragments inside paragraphs. Cleans the body before
        signature operations to avoid duplicating junk content.
        """
        if not body_html:
            return ""
        garbage_pattern = re.compile(
            r"<p[^>]*>.*?(?:&lt;div|\&amp;lt;div).*?</p>",
            re.I | re.S,
        )
        return garbage_pattern.sub("", body_html)

    def _remove_signature_by_value(self, body_html, signature_html):
        """
        Removes an existing signature by matching the raw HTML and escaped
        variants, leaving the remaining body intact. Supports reapplying a
        different signature without stacking previous versions.
        """
        if not body_html or not signature_html:
            return body_html or ""
        sig = (signature_html or "").strip()
        if not sig:
            return body_html
        body_html = body_html.replace(sig, "")
        esc1 = html.escape(sig)
        body_html = body_html.replace(esc1, "")
        esc2 = html.escape(esc1)
        body_html = body_html.replace(esc2, "")
        return body_html

    def _remove_existing_signature(self, body_html):
        """
        Locates the MailDesk signature container within the HTML and removes it
        or trims content before the marker. Prevents multiple signature blocks
        from accumulating when recomposing messages.
        """
        if not body_html:
            return ""
        body_html = html.unescape(body_html or "")
        lower_body = body_html.lower()
        marker = "o-signature-container"
        pos = lower_body.find(marker)
        if pos == -1:
            return body_html
        start_div = lower_body.rfind("<div", 0, pos)
        if start_div == -1:
            return body_html[:pos]
        return body_html[:start_div]

    def _append_signature(self, body_html, signature_html):
        """
        Inserts a sanitized signature block into the body, ensuring existing
        signatures are removed and spacing is appropriate. If the body is empty
        it returns only the signature container; otherwise it appends the block
        after adding trailing breaks.
        """
        body_html = html.unescape(body_html or "")
        signature_html = html.unescape((signature_html or "").strip())
        body_html = self._remove_existing_signature(body_html)
        container = (
            f'<div class="o-signature-container o-dont-touch">{signature_html}</div>'
        )
        if not signature_html:
            return body_html
        if self._is_html_effectively_empty(body_html):
            return container
        body_html = body_html.rstrip()
        if not re.search(r"(<br\s*/?>\s*){1,2}$", body_html, re.I):
            body_html += "<br><br>"
        return body_html + container

    @api.onchange("account_id")
    def _onchange_account_id(self):
        """
        Updates the composer display name and signature when the mailbox account
        changes. Cleans existing body noise, drops old signatures, and applies
        the selected account's signature when enabled so outgoing messages
        reflect the new sender identity.
        """
        for wizard in self:
            if wizard.account_id:
                wizard.custom_from_name = (
                    wizard.account_id.sender_name
                    or wizard.account_id.name
                    or wizard.env.user.name
                )
            else:
                wizard.custom_from_name = wizard.env.user.name

            body = wizard.body or ""
            body = wizard._remove_html_garbage_block(body)
            body = wizard._remove_existing_signature(body)

            if not wizard.email_add_signature:
                wizard.body = body
                continue

            if wizard.account_id and wizard.account_id.signature:
                body = wizard._remove_signature_by_value(
                    body, wizard.account_id.signature
                )
                body = wizard._append_signature(body, wizard.account_id.signature)

            wizard.body = body
