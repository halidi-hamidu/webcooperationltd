# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
MIME Builder: Constructs EmailMessage objects for sending.

Handles:
- Header generation (From, To, Subject, Message-ID, etc.)
- HTML-to-text conversion
- Attachment processing (regular + inline/CID)
- Proper MIME structure (multipart/mixed → multipart/alternative → multipart/related)

ARCHITECTURAL INVARIANT (enforced externally):
- Inline attachments MUST have content_id field set before reaching this builder
- No heuristic matching - this layer is DETERMINISTIC
- CID normalization happens in NormalizeOutgoingHtml service (application layer)

This is infrastructure layer - executes deterministically based on prepared inputs.
"""

import base64
import logging
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from bs4 import BeautifulSoup

from ...domain.services.normalization import build_references_header, msgid_header

_logger = logging.getLogger(__name__)


class MimeBuilder:
    """Builds MIME messages for email sending (deterministic, no heuristics)."""

    def __init__(self, env):
        """
        Initialize MimeBuilder.

        Args:
            env: Odoo environment for accessing attachments
        """
        self._env = env

    def build(
        self,
        account,
        subject,
        body_html,
        to,
        cc=None,
        bcc=None,
        reply_message_id=None,
        reply_references=None,
        attachment_ids=None,
        request_delivery_receipt=False,
        request_read_receipt=False,
        from_display=False,
        outgoing_id=None,
    ):
        """
        Build an EmailMessage object with proper inline image support.

        EXPECTS (enforced by caller):
        - body_html has normalized cid: references (cid:{att_id}@maildesk)
        - Inline attachments have content_id field set

        Args:
            account: mailbox.account record
            subject: Email subject
            body_html: HTML body content (PRE-NORMALIZED by NormalizeOutgoingHtml)
            to: List of To addresses
            cc: List of CC addresses
            bcc: List of BCC addresses
            reply_message_id: Message-ID to reply to (In-Reply-To)
            attachment_ids: List of ir.attachment IDs
            request_delivery_receipt: Boolean
            request_read_receipt: Boolean
            from_display: Optional sender display name override

        Returns:
            Tuple[EmailMessage, str]: Built message and its Message-ID
        """

        def clean(v):
            import re

            return re.sub(r"[\r\n]+", " ", str(v or "")).strip()

        def parse_addr(lst):
            import re

            if not lst:
                return ""
            out = []
            for raw in lst:
                s = raw.strip()
                m = re.match(r"^(.*?)\s*<([^>]+)>$", s)
                if m:
                    out.append(formataddr((clean(m.group(1)), clean(m.group(2)))))
                else:
                    out.append(clean(s))
            return ", ".join(out)

        def html2text(html):
            if not BeautifulSoup:
                return ""
            soup = BeautifulSoup(html or "", "html.parser")
            for t in soup(
                ["style", "script", "head", "meta", "link", "svg", "noscript"]
            ):
                t.decompose()
            for a in soup.find_all("a", href=True):
                t = a.get_text(strip=True) or a["href"]
                a.string = t
                a.insert_after(f" ({a['href']})")
            txt = soup.get_text(separator="\n").strip()
            import re

            return re.sub(r"\n{3,}", "\n\n", txt)

        # === HEADERS ===
        msg = EmailMessage()
        msg_id = make_msgid(domain=(account.email or "local").split("@")[-1])

        frm = formataddr(
            (
                clean(from_display or account.sender_name or account.name),
                clean(account.email),
            )
        )

        msg["Subject"] = clean(subject)
        msg["From"] = frm
        to_hdr = parse_addr(to)
        if to_hdr:
            msg["To"] = to_hdr
        cc_hdr = parse_addr(cc)
        if cc_hdr:
            msg["Cc"] = cc_hdr

        msg["Message-ID"] = msg_id
        msg["X-Original-Message-ID"] = msg_id
        msg["User-Agent"] = "MailDesk"
        msg["Date"] = formatdate(localtime=False, usegmt=True)
        msg["MIME-Version"] = "1.0"

        if outgoing_id:
            msg["X-MailDesk-Outgoing-ID"] = clean(outgoing_id)

        in_reply_to = msgid_header(reply_message_id)
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            references = build_references_header(
                reply_references or "", reply_message_id
            )
            if references:
                msg["References"] = references

        if request_delivery_receipt:
            msg["Return-Receipt-To"] = clean(account.email)
        if request_read_receipt:
            msg["Disposition-Notification-To"] = clean(account.email)

        # === ATTACHMENT CLASSIFICATION (deterministic) ===
        inline_attachments = []
        regular_attachments = []

        if attachment_ids:
            attachments = self._env["ir.attachment"].sudo().browse(attachment_ids)

            for att in attachments:
                # DETERMINISTIC: attachment has content_id → inline
                # No content_id → regular
                if att.content_id:
                    inline_attachments.append(att)
                    _logger.debug(
                        f"[MIME Builder] Inline: {att.name} (cid:{att.content_id})"
                    )
                else:
                    regular_attachments.append(att)

        # === MIME STRUCTURE ===
        plain = html2text(body_html) if body_html else ""

        if inline_attachments:
            # Complex structure: multipart/mixed → multipart/alternative → multipart/related
            msg.set_content(plain or "", subtype="plain", charset="utf-8")

            # Add HTML alternative
            msg.add_alternative(body_html or "", subtype="html", charset="utf-8")

            # Get the HTML part we just created (it's the last alternative)
            # msg.get_payload() returns list of parts, last one is HTML
            html_part = msg.get_payload()[-1]

            # Convert HTML part to multipart/related for inline images
            html_part.make_related()

            # Add inline images to the HTML alternative
            for att in inline_attachments:
                self._add_inline_attachment(html_part, att)

            # Add regular attachments to root message
            for att in regular_attachments:
                self._add_regular_attachment(msg, att)

        else:
            # Simple structure: multipart/alternative (text + HTML)
            msg.set_content(plain or "", subtype="plain", charset="utf-8")
            msg.add_alternative(body_html or "", subtype="html", charset="utf-8")

            # Add all attachments as regular
            for att in regular_attachments:
                self._add_regular_attachment(msg, att)

        _logger.info(
            f"[MIME Builder] Built message: {len(inline_attachments)} inline, "
            f"{len(regular_attachments)} regular attachments"
        )

        return msg, msg_id

    def _add_inline_attachment(self, html_part, attachment):
        """
        Add an inline image attachment to the HTML part.

        EXPECTS: attachment.content_id already set (by NormalizeOutgoingHtml).

        Args:
            html_part: EmailMessage alternative part for HTML
            attachment: ir.attachment record with content_id set
        """
        if not attachment.content_id:
            _logger.error(
                f"[MIME Builder] INVARIANT VIOLATION: Inline attachment {attachment.id} "
                f"has no content_id (this should have been set by NormalizeOutgoingHtml)"
            )
            # Fallback: treat as regular attachment
            return

        data = base64.b64decode(attachment.datas or b"")
        mimetype = attachment.mimetype or "application/octet-stream"

        if "/" in mimetype:
            maintype, subtype = mimetype.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"

        # Add attachment with Content-ID and inline disposition
        # EmailMessage.add_related() automatically:
        # - Sets Content-ID header
        # - Sets Content-Disposition: inline
        # - Adds to multipart/related structure
        html_part.add_related(
            data,
            maintype=maintype,
            subtype=subtype,
            cid=attachment.content_id,  # EmailMessage wraps with angle brackets
            filename=attachment.name or "image",
        )

        _logger.debug(
            f"[MIME Builder] Added inline: {attachment.name} "
            f"(Content-ID: <{attachment.content_id}>, {len(data)} bytes)"
        )

    def _add_regular_attachment(self, msg, attachment):
        """
        Add a regular (non-inline) attachment to the message.

        Args:
            msg: EmailMessage root
            attachment: ir.attachment record
        """
        data = base64.b64decode(attachment.datas or b"")
        mimetype = attachment.mimetype or "application/octet-stream"

        if "/" in mimetype:
            maintype, subtype = mimetype.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"

        msg.add_attachment(
            data, maintype=maintype, subtype=subtype, filename=attachment.name or "file"
        )

        _logger.debug(
            f"[MIME Builder] Added regular: {attachment.name} ({len(data)} bytes)"
        )
