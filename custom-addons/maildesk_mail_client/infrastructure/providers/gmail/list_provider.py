# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk List Provider.

Implements infrastructure integration for List Provider (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

import logging
import re

from odoo import fields

from ....infrastructure.rendering.ui_formatting import (
    avatar_html,
    display_name_from_email,
)
from ....application.services.display_formatting import format_sender_display
from ....infrastructure.utils.email_utils import (
    decode_header_value,
    parse_sender_header,
)
from ....adapters.gmail_adapter import GmailAdapter
from ....adapters.legacy_mapper import message_to_legacy_dict

_logger = logging.getLogger(__name__)


def gmail_fetch_meta_batch(
    env, sync_self, service, account, folder, ids, partner_cache
):
    """
    Fetch Gmail message metadata for a batch of message IDs.

    Args:
        env: Odoo environment
        sync_self: IGNORED (kept for signature compat temporarily, or removed if caller updated)
        service: Gmail API service
        account: Account record
        folder: Folder record
        ids: List of Gmail message IDs
        partner_cache: Partner lookup cache

    Returns:
        list: Message records with metadata
    """
    if not ids:
        return []

    fld = folder or False
    folder_name = (
        getattr(fld, "imap_name", None) or getattr(fld, "name", None) or "ALL_MAIL"
    )

    # Facade to provide helper methods for GmailAdapter
    class GmailFacade:
        def _decode_header_value(self, h):
            return decode_header_value(h)

        def _parse_sender_header(self, h):
            return parse_sender_header(h)

    adapter = GmailAdapter(GmailFacade())

    try:
        msgs = adapter.fetch_metadata_batch(service, account.id, folder_name, ids)
    except Exception as e:
        _logger.debug("gmail_fetch_meta_batch error: %s", e)
        return []

    recs = []
    for m in msgs:
        # Convert to legacy dict
        rec = message_to_legacy_dict(m)

        # Enrich with Partner info (Legacy behavior - preserve this separation)
        # The adapter returned raw header info. We resolve partner here.
        email_from = rec["from_addr"]
        partner = partner_cache.get(email_from)
        if partner is None:
            partner = env["res.partner"].search(
                [("email", "=ilike", email_from)], limit=1
            )
            partner_cache[email_from] = partner

        sender_name = partner.name if partner else m.sender_display_name
        # Update legacy dict with resolved display name
        rec["sender_display_name"] = format_sender_display(sender_name, email_from)

        # Add UI overlays (avatar)
        rec["avatar_html"] = avatar_html(email_from, partner, display_name_from_email)
        rec["avatar_partner_id"] = partner.id if partner else False
        rec["message_id_norm"] = m.message_header_id  # Adapter normalized it
        rec["msg_key"] = f"{account.id}|{fld.id if fld else ''}|{str(m.id)}"

        # Restore other keys if legacy_mapper missed them
        rec["tag_ids"] = []
        rec["is_draft"] = False
        rec["preview_text"] = rec["preview"]

        # Format date for UI
        if m.date:
            try:
                dt_ctx = fields.Datetime.context_timestamp(env["mailbox.sync"], m.date)
                rec["formatted_date"] = dt_ctx.strftime("%d %b %Y %H:%M")
            except Exception:
                rec["formatted_date"] = ""
        else:
            rec["formatted_date"] = ""

        # Critical: Ensure account, backend type and folder ID are present for JS logic
        rec["account_id"] = [account.id, account.name]
        rec["backend_type"] = "gmail"
        rec["folder_id"] = fld.id if fld else False

        recs.append(rec)

    return recs


def gmail_query_from_filters(
    env, sync_self, account=None, flt=None, text=None, partner_id=None, email_from=None
):
    parts = []
    me = (account.email or "").strip().lower() if account else ""
    if flt == "unread":
        parts.append("is:unread")
    elif flt == "starred":
        parts.append("is:starred")
    elif flt == "incoming":
        if me:
            parts.append(f"-from:{me}")
    elif flt == "outgoing":
        if me:
            parts.append(f"from:{me}")
    if partner_id and not email_from:
        partner = env["res.partner"].browse(partner_id)
        if partner and partner.email:
            email_from = partner.email
    if email_from:
        parts.append(f"from:{email_from}")
    if text:
        s = re.sub(r"\s+", " ", text.strip())
        if s:
            parts.append(s)
    return " ".join(parts).strip()


def gmail_unread_counts(env, sync_self, service, account, folder, q):
    folder_name = (
        getattr(folder, "imap_name", None) or getattr(folder, "name", None) or ""
    ).strip()
    norm = folder_name.lower().replace("[gmail]/", "").strip()

    SYSTEM_LABELS = {
        "inbox": "INBOX",
        "sent": "SENT",
        "sent mail": "SENT",
        "important": "IMPORTANT",
        "trash": "TRASH",
        "bin": "TRASH",
        "deleted": "TRASH",
        "draft": "DRAFT",
        "drafts": "DRAFT",
        "spam": "SPAM",
        "starred": "STARRED",
    }

    if norm in SYSTEM_LABELS:
        label_id = SYSTEM_LABELS[norm]
        try:
            lab = service.users().labels().get(userId="me", id=label_id).execute()
            unread_total = int(lab.get("messagesUnread") or 0)
        except Exception:
            unread_total = 0
    else:
        unread_total = None

    if unread_total is None:
        if norm in SYSTEM_LABELS:
            folder_filter = f"in:{norm}"
        else:
            folder_filter = f'label:"{folder_name}"'

        total_q = f"is:unread {folder_filter} -in:spam -in:trash"

        cnt_total = 0
        params = {
            "userId": "me",
            "q": total_q,
            "maxResults": 500,
            "includeSpamTrash": False,
            "fields": "nextPageToken,messages/id",
        }
        req = service.users().messages().list(**params)

        while req is not None:
            resp = req.execute()
            cnt_total += len(resp.get("messages", []) or [])
            npt = resp.get("nextPageToken")
            if not npt:
                break
            params["pageToken"] = npt
            req = service.users().messages().list(**params)

        unread_total = cnt_total

    q_unread = (q or "").strip()
    if "is:unread" not in q_unread:
        q_unread = "is:unread " + q_unread

    if norm in SYSTEM_LABELS:
        q_unread = f"in:{norm} " + q_unread
    else:
        q_unread = f'label:"{folder_name}" ' + q_unread

    cnt_filtered = 0
    params = {
        "userId": "me",
        "q": q_unread,
        "maxResults": 500,
        "includeSpamTrash": False,
        "fields": "nextPageToken,messages/id",
    }

    req = service.users().messages().list(**params)
    while req is not None:
        resp = req.execute()
        cnt_filtered += len(resp.get("messages", []) or [])
        npt = resp.get("nextPageToken")
        if not npt:
            break
        params["pageToken"] = npt
        req = service.users().messages().list(**params)

    return unread_total, cnt_filtered
