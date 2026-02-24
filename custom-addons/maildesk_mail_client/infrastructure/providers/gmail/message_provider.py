# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Gmail Message Provider

Gmail API full message fetching with bodies, attachments, and threading.
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
from ....infrastructure.rendering.html_sanitizer import strip_html_to_text
from ....infrastructure.rendering.ui_formatting import (
    avatar_html,
    display_name_from_email,
)
from ....application.services.display_formatting import format_sender_display

_logger = logging.getLogger(__name__)


def gmail_get_message_full(
    env,
    sync_self,
    service,
    account,
    folder,
    message_id,
    gmail_get_thread_full_func,
):
    """
    Fetch full Gmail message with body, attachments, and thread context.

    Args:
        env: Odoo environment
        sync_self: IGNORED
        service: Gmail API service
        account: Account record
        folder: Folder record
        message_id: Gmail message ID
        gmail_get_thread_full_func: Function to fetch thread
    """
    LOGP = "[GMAIL msg_full]"

    _logger.info(
        "%s start message_id=%s account_id=%s folder=%s",
        LOGP,
        message_id,
        getattr(account, "id", None),
        folder,
    )

    meta = (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["Subject"],
        )
        .execute()
    )
    thread_id = meta.get("threadId")

    chain = gmail_get_thread_full_func(
        env, sync_self, service, account, thread_id, include_bodies=True
    )

    cur = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    payload = cur.get("payload", {}) or {}
    headers_list = payload.get("headers") or []
    headers = {
        (h.get("name") or "").lower(): (h.get("value") or "") for h in headers_list
    }
    labels = set(cur.get("labelIds") or [])
    ts = int(cur.get("internalDate") or "0")
    if ts:
        dt = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).replace(tzinfo=None)
    else:
        dt = datetime(1970, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)

    def _hdr_from_part(h_list, name):
        name = (name or "").lower()
        for h in h_list or []:
            if (h.get("name") or "").lower() == name:
                return h.get("value") or ""
        return ""

    def _content_id(h_list):
        v = _hdr_from_part(h_list, "content-id")
        return v.strip("<>").strip() if v else ""

    def _disp_token(h_list):
        v = _hdr_from_part(h_list, "content-disposition")
        return v.split(";", 1)[0].strip().lower() if v else ""

    def _add_text(html_ref, text_ref, mime, raw_bytes):
        if not raw_bytes:
            return html_ref, text_ref
        mime = (mime or "").lower()
        if mime.startswith("text/html"):
            html_ref += raw_bytes.decode("utf-8", "ignore")
        elif mime.startswith("text/plain") and not text_ref:
            text_ref = raw_bytes.decode("utf-8", "ignore")
        return html_ref, text_ref

    _, disp_name, email_from = parse_sender_header(
        headers.get("from") or "", display_name_from_email
    )
    email_from = (email_from or "").lower()

    partner = env["res.partner"].search([("email", "=ilike", email_from)], limit=1)
    _logger.info("%s partner.lookup email=%s found=%s", LOGP, email_from, bool(partner))

    html_body = ""
    text_body = ""
    attachments = []

    stack = [payload] if payload else []
    while stack:
        part = stack.pop()
        subparts = part.get("parts")
        if subparts:
            stack.extend(subparts)
            continue

        mime = (part.get("mimeType") or "").lower()

        body = part.get("body") or {}
        data = body.get("data")
        att_id = body.get("attachmentId")
        filename = (part.get("filename") or "").strip()
        part_headers = part.get("headers") or []
        disp_tok = _disp_token(part_headers)

        if mime == "message/rfc822":
            raw_eml = b""
            if data:
                try:
                    raw_eml = base64.urlsafe_b64decode(data.encode("utf-8"))
                except Exception:
                    raw_eml = b""

            if att_id and not raw_eml:
                name = filename or "message.eml"
                full_mime = mime or "message/rfc822"
                size = body.get("size") or 0
                cid = _content_id(part_headers)
                attachments.append(
                    {
                        "provider": "gmail",
                        "provider_message_id": str(cur.get("id") or message_id or ""),
                        "provider_attachment_id": str(att_id or ""),
                        "name": name,
                        "filename": name,
                        "mimetype": full_mime,
                        "size": int(size or 0),
                        "content_id": cid or "",
                        "contentId": cid or "",
                        "is_inline": False,
                    }
                )
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
                    _logger.info("%s rfc822.parse error: %s", LOGP, e)
            continue

        if att_id and mime.startswith("text/") and disp_tok != "attachment":
            try:
                fetched = (
                    service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=message_id, id=att_id)
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
            or _content_id(part_headers)
            or disp_tok in ("inline", "attachment")
        ):
            full_mime = part.get("mimeType") or "application/octet-stream"
            size = body.get("size") or 0
            cid = _content_id(part_headers)
            name = filename or cid or f"attachment-{att_id}"
            attachments.append(
                {
                    "provider": "gmail",
                    "provider_message_id": str(cur.get("id") or message_id or ""),
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
        snippet = (cur.get("snippet") or "").strip()
        if snippet:
            text_body = snippet

    sender_name = partner.name if partner else display_name_from_email(email_from)
    rec = {
        "id": cur["id"],
        "subject": headers.get("subject") or "(no subject)",
        "email_from": email_from,
        "sender_display_name": format_sender_display(sender_name, email_from),
        "date": dt,
        "formatted_date": fields.Datetime.context_timestamp(
            env["mailbox.sync"], dt
        ).strftime("%d %b %Y %H:%M"),
        "body_original": html_body
        or (("<pre>" + Markup.escape(text_body) + "</pre>") if text_body else ""),
        "body_plain": (
            text_body
            or (
                strip_html_to_text(html_body)
                if html_body
                else (cur.get("snippet") or "")
            )
        ),
        "is_read": "UNREAD" not in labels,
        "is_starred": "STARRED" in labels,
        "has_attachments": bool(attachments or ("HAS_ATTACHMENTS" in labels)),
        "attachments": attachments,
        "to_display": decode_header_value(headers.get("to") or ""),
        "cc_display": decode_header_value(headers.get("cc") or ""),
        "bcc_display": decode_header_value(headers.get("bcc") or ""),
        "account_id": [account.id, account.name],
        # avatar_html is NOT used in message_provider.py return (only list_provider enriched it?)
        # Let's check original. It returned 'avatar_html': sync_self._avatar_html(...).
        "avatar_html": avatar_html(email_from, partner, display_name_from_email),
        "avatar_partner_id": partner.id if partner else False,
        "model": False,
        "res_id": False,
        "tag_ids": False,
        "in_reply_to": (headers.get("in-reply-to") or "").strip(),
        "message_id": (headers.get("message-id") or "").strip(),
        "backend_type": "gmail",
        "folder_id": folder.id if folder else False,
    }

    def _norm_mid(x):
        return (x or "").strip().lower()

    def _build_ancestors_only(thread_msgs, cur_in_reply_to):
        by_mid = {
            _norm_mid(m.get("message_id")): m
            for m in (thread_msgs or [])
            if m.get("message_id")
        }
        res, seen = [], set()
        mid = _norm_mid(cur_in_reply_to)
        while mid and mid not in seen:
            seen.add(mid)
            m = by_mid.get(mid)
            if not m:
                break
            res.append(m)
            mid = _norm_mid(m.get("in_reply_to"))
        res.sort(
            key=lambda m: (
                fields.Datetime.to_datetime(m.get("date") or "1970-01-01").replace(
                    tzinfo=None
                )
                if m.get("date")
                else datetime(1970, 1, 1)
            ),
            reverse=True,
        )
        return res

    chain_wo_current = [r for r in (chain or []) if r.get("id") != message_id]
    ancestors = _build_ancestors_only(chain_wo_current, rec.get("in_reply_to"))
    rec["parent_chain"] = ancestors or False

    _logger.info(
        "%s done | html_len=%d plain_len=%d atts=%d labels=%s",
        LOGP,
        len(rec["body_original"] or ""),
        len(rec["body_plain"] or ""),
        len(attachments),
        list(labels)[:6],
    )

    return rec
