# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Message Provider.

Implements infrastructure integration for Message Provider (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from odoo import fields

from ...rendering.ui_formatting import (
    avatar_html,
    display_name_from_email,
)
from ....application.services.display_formatting import format_sender_display

_logger = logging.getLogger(__name__)


def _graph_dt(dt):
    # Duplicated helper for robustness/independence from list_provider import loops
    if not dt:
        return None

    s = str(dt).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        val = datetime.fromisoformat(s)
    except Exception:
        return None
    return val.astimezone(timezone.utc).replace(tzinfo=None) if val.tzinfo else val


def outlook_get_message_full(
    env, sync_self, sess, base_url, account, folder, message_id, update_cache=True
):
    sel = (
        "id,subject,from,toRecipients,ccRecipients,bccRecipients,"
        "receivedDateTime,hasAttachments,isRead,importance,flag,"
        "internetMessageId,conversationId,body,bodyPreview,internetMessageHeaders"
    )
    url_msg = f"{base_url}/me/messages/{message_id}?$select={sel}"

    atts = []
    url_atts = (
        f"{base_url}/me/messages/{message_id}/attachments"
        "?$top=50&$select=id,name,contentType,size,isInline,contentId"
    )
    try:
        r2 = sess.get(url_atts, timeout=20)
        if r2.status_code >= 400:
            url_atts_fallback = (
                f"{base_url}/me/messages/{message_id}/attachments?$top=50"
            )
            r2 = sess.get(url_atts_fallback, timeout=20)
        r2.raise_for_status()
        data = r2.json() or {}
        atts = data.get("value", [])
    except Exception:
        atts = []

    r = sess.get(url_msg, timeout=30)
    r.raise_for_status()
    m = r.json()

    headers = m.get("internetMessageHeaders") or []
    in_reply_to_raw = ""
    references_raw = ""
    for h in headers:
        name = (h.get("name") or "").lower()
        value = h.get("value") or ""
        if name == "in-reply-to":
            in_reply_to_raw = value
        elif name == "references":
            references_raw = value

    body = m.get("body") or {}
    body_html = body.get("content") or ""
    try:
        body_plain = BeautifulSoup(body_html, "lxml").get_text("\n", strip=True)
    except Exception:
        body_plain = BeautifulSoup(body_html, "html.parser").get_text("\n", strip=True)

    attachments_json = []
    for att in atts:
        att_id = att.get("id")
        if not att_id:
            continue

        name = att.get("name") or "attachment"
        mime = (att.get("contentType") or "application/octet-stream").lower()
        size = att.get("size") or 0
        cid_raw = att.get("contentId") or ""
        is_inline = bool(att.get("isInline"))
        attachments_json.append(
            {
                "provider": "outlook",
                "provider_message_id": str(message_id or ""),
                "provider_attachment_id": str(att_id or ""),
                "name": name,
                "filename": name,
                "mimetype": mime,
                "size": int(size or 0),
                "content_id": (cid_raw or "").strip("<>").strip(),
                "contentId": (cid_raw or "").strip("<>").strip(),
                "is_inline": bool(is_inline),
            }
        )

    sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "") or ""
    email_from = sender.lower()

    partner = env["res.partner"].search([("email", "=ilike", email_from)], limit=1)

    dt_raw = (
        m.get("receivedDateTime") or m.get("sentDateTime") or m.get("createdDateTime")
    )
    msg_dt = _graph_dt(dt_raw)

    if msg_dt:
        # Use sync_self context for timezone
        user_dt = fields.Datetime.context_timestamp(sync_self, msg_dt)
        date_user = user_dt.strftime("%Y-%m-%d %H:%M:%S")
        formatted_date = user_dt.strftime("%d %b %Y %H:%M")
    else:
        date_user = False
        formatted_date = "—"

    flag = (m.get("flag") or {}).get("flagStatus")
    is_starred = flag == "flagged"

    rec = {
        "id": message_id,
        "subject": m.get("subject") or "(no subject)",
        "email_from": email_from,
        "date": date_user,
        "formatted_date": formatted_date,
        "body_original": body_html,
        "body_plain": body_plain,
        "body_html": body_html,
        "body_text": body_plain,
        "is_read": bool(m.get("isRead")),
        "is_starred": is_starred,
        "has_attachments": bool(attachments_json) or bool(m.get("hasAttachments")),
        "attachments": attachments_json,
        "account_display": (
            f"{account.name} | {account.email}"
            if account.name != account.email
            else account.email
        ),
        "to_display": ", ".join(
            [
                (x.get("emailAddress") or {}).get("address", "")
                for x in (m.get("toRecipients") or [])
            ]
        ),
        "cc_display": ", ".join(
            [
                (x.get("emailAddress") or {}).get("address", "")
                for x in (m.get("ccRecipients") or [])
            ]
        ),
        "bcc_display": ", ".join(
            [
                (x.get("emailAddress") or {}).get("address", "")
                for x in (m.get("bccRecipients") or [])
            ]
        ),
        "account_id": [account.id, account.name],
        "is_draft": False,
        "avatar_html": avatar_html(email_from, partner, display_name_from_email),
        "avatar_partner_id": partner.id if partner else False,
        "backend_type": "outlook",
        "folder_id": folder.id if folder else False,
        "tag_ids": [],
        "sender_display_name": format_sender_display(
            partner.name if partner else display_name_from_email(email_from),
            email_from,
        ),
        "partner_trusted": partner.trusted_partner if partner else False,
        "trusted_by_user_id": False,
        "in_reply_to": in_reply_to_raw,
        "message_id": (m.get("internetMessageId") or "").strip("<>"),
        "references_hdr": references_raw,
    }

    return rec
