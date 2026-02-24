# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Gmail Thread Provider

Gmail API thread fetching with full message bodies and attachments.
"""

import base64
import logging
from datetime import datetime, timezone
from email import message_from_bytes, policy

from markupsafe import Markup
from odoo import fields

from ....domain.services.normalization import (
    decode_header_value,
    parse_sender_header,
)
from ...rendering.html_sanitizer import strip_html_to_text
from ...rendering.ui_formatting import (
    display_name_from_email,
)
from ....application.services.display_formatting import format_sender_display
from ...serialization.message_enricher import enrich_with_partner_meta

_logger = logging.getLogger(__name__)


def gmail_get_thread_full(
    env, sync_self, service, account, thread_id, include_bodies=False
):
    """
    Fetch full Gmail thread with all messages and optionally their bodies/attachments.

    Args:
        env: Odoo environment
        sync_self: MailboxSync instance (for method delegation)
        service: Gmail API service
        account: Account record
        thread_id: Gmail thread ID
        include_bodies: Whether to fetch full bodies and attachments

    Returns:
        list: Thread messages with metadata and optionally bodies
    """
    t = (
        service.users()
        .threads()
        .get(
            userId="me",
            id=thread_id,
            format="full" if include_bodies else "metadata",
        )
        .execute()
    )

    def _add_text(html_body_ref, text_body_ref, mime, raw_bytes):
        if not raw_bytes:
            return html_body_ref, text_body_ref
        mime = (mime or "").lower()
        if mime.startswith("text/html"):
            html_body_ref += raw_bytes.decode("utf-8", "ignore")
        elif mime.startswith("text/plain") and not text_body_ref:
            text_body_ref = raw_bytes.decode("utf-8", "ignore")
        return html_body_ref, text_body_ref

    def _content_id(headers_list):
        try:
            for h in headers_list or []:
                if (h.get("name") or "").lower() == "content-id":
                    v = (h.get("value") or "").strip()
                    return v.strip("<>").strip()
        except Exception as e:
            _logger.debug("ignored error: %s", e)
        return ""

    def _disp_token(headers_list):
        try:
            for h in headers_list or []:
                if (h.get("name") or "").lower() == "content-disposition":
                    v = (h.get("value") or "").strip()
                    return (v.split(";", 1)[0] or "").strip().lower()
        except Exception as e:
            _logger.debug("ignored error: %s", e)
        return ""

    msgs = t.get("messages", []) or []
    out = []
    partner_cache = {}

    for m in msgs:
        payload = m.get("payload", {}) or {}
        headers_list = payload.get("headers") or []
        hs = {
            (h.get("name") or "").lower(): (h.get("value") or "") for h in headers_list
        }

        lbls = set(m.get("labelIds") or [])
        ts = int(m.get("internalDate") or "0")
        if ts:
            dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).replace(
                tzinfo=None
            )
        else:
            dt = datetime(1970, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)

        _, disp_name, email_from = parse_sender_header(
            hs.get("from") or "", display_name_from_email
        )
        email_from = (email_from or "").lower()

        partner = partner_cache.get(email_from)
        if partner is None:
            partner = env["res.partner"].search(
                [("email", "=ilike", email_from)], limit=1
            )
            partner_cache[email_from] = partner

        html_body = ""
        text_body = ""
        attachments = []
        has_atts = "HAS_ATTACHMENTS" in lbls

        if include_bodies:
            stack = [payload] if payload else []
            while stack:
                p = stack.pop()
                subparts = p.get("parts")
                if subparts:
                    stack.extend(subparts)
                    continue

                mime = (p.get("mimeType") or "").lower()
                body = p.get("body") or {}
                data = body.get("data")
                att_id = body.get("attachmentId")
                filename = (p.get("filename") or "").strip()
                p_headers = p.get("headers") or []
                disp_tok = _disp_token(p_headers)

                if mime == "message/rfc822":
                    raw_eml = b""
                    if data:
                        try:
                            raw_eml = base64.urlsafe_b64decode(data.encode("utf-8"))
                        except Exception:
                            raw_eml = b""

                    if att_id and not raw_eml:
                        name = filename or "message.eml"
                        full_mime = mime
                        size = body.get("size") or 0
                        cid = _content_id(p_headers)
                        attachments.append(
                            {
                                "provider": "gmail",
                                "provider_message_id": str(m.get("id") or ""),
                                "provider_attachment_id": str(att_id or ""),
                                "name": name,
                                "filename": name,
                                "mimetype": full_mime or "message/rfc822",
                                "size": int(size or 0),
                                "content_id": cid or "",
                                "contentId": cid or "",
                                "is_inline": False,
                            }
                        )
                        has_atts = True
                        continue

                    if raw_eml:
                        try:
                            em = message_from_bytes(raw_eml, policy=policy.default)

                            def walk_em(msg):
                                if msg.is_multipart():
                                    for sp in msg.iter_parts():
                                        yield from walk_em(sp)
                                else:
                                    yield msg

                            for sp in walk_em(em):
                                smime = (sp.get_content_type() or "").lower()
                                raw = sp.get_payload(decode=True) or b""
                                html_body, text_body = _add_text(
                                    html_body, text_body, smime, raw
                                )
                        except Exception as e:
                            _logger.debug("ignored error: %s", e)
                    continue

                if att_id and mime.startswith("text/") and disp_tok != "attachment":
                    try:
                        fetched = (
                            service.users()
                            .messages()
                            .attachments()
                            .get(
                                userId="me",
                                messageId=m["id"],
                                id=att_id,
                            )
                            .execute()
                        )
                        raw_b64 = fetched.get("data")
                        raw = (
                            base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
                            if raw_b64
                            else b""
                        )
                    except Exception:
                        raw = b""
                    html_body, text_body = _add_text(html_body, text_body, mime, raw)
                    continue

                if data and mime.startswith("text/"):
                    try:
                        raw = base64.urlsafe_b64decode(data.encode("utf-8"))
                    except Exception:
                        raw = b""
                    html_body, text_body = _add_text(html_body, text_body, mime, raw)
                    continue

                if att_id and (
                    filename
                    or _content_id(p_headers)
                    or disp_tok in ("inline", "attachment")
                ):
                    has_atts = True
                    full_mime = mime or "application/octet-stream"
                    size = body.get("size") or 0
                    cid = _content_id(p_headers)
                    name = filename or cid or f"attachment-{att_id}"
                    attachments.append(
                        {
                            "provider": "gmail",
                            "provider_message_id": str(m.get("id") or ""),
                            "provider_attachment_id": str(att_id or ""),
                            "name": name,
                            "filename": name,
                            "mimetype": full_mime,
                            "size": int(size or 0),
                            "content_id": cid or "",
                            "contentId": cid or "",
                            "is_inline": disp_tok == "inline",
                        }
                    )
                    continue

            if not html_body and text_body:
                html_body = "<pre>" + Markup.escape(text_body) + "</pre>"
            if not html_body and not text_body:
                snip = (m.get("snippet") or "").strip()
                if snip:
                    text_body = snip

        _logger.info(
            "Gmail thread message: id=%s include_bodies=%s html_body_len=%s text_body_len=%s",
            m.get("id"),
            include_bodies,
            len(html_body),
            len(text_body),
        )

        sender_name = partner.name if partner else display_name_from_email(email_from)
        rec = {
            "id": m["id"],
            "threadId": t["id"],
            "subject": hs.get("subject") or "(no subject)",
            "email_from": email_from,
            "sender_display_name": format_sender_display(sender_name, email_from),
            "date": dt,
            "formatted_date": fields.Datetime.context_timestamp(env.user, dt).strftime(
                "%d %b %Y %H:%M"
            ),
            "body_original": html_body if include_bodies else "",
            "body_html": html_body
            if include_bodies
            else "",  # Frontend expects body_html
            "body_plain": (
                text_body
                or (
                    strip_html_to_text(html_body)
                    if include_bodies and html_body
                    else (m.get("snippet") or "")
                )
            ),
            "is_read": "UNREAD" not in lbls,
            "is_starred": "STARRED" in lbls,
            "has_attachments": has_atts,
            "attachments": attachments if include_bodies else [],
            "to_display": decode_header_value(hs.get("to") or ""),
            "cc_display": decode_header_value(hs.get("cc") or ""),
            "bcc_display": decode_header_value(hs.get("bcc") or ""),
            "account_id": [account.id, account.name],
            "avatar_html": "",
            "avatar_partner_id": False,
            "in_reply_to": hs.get("in-reply-to") or "",
            "message_id": hs.get("message-id") or "",
        }
        rec = enrich_with_partner_meta(rec, env)
        out.append(rec)

    out.sort(key=lambda x: x["date"], reverse=True)

    return out
