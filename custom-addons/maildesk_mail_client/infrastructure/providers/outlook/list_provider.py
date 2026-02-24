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
from datetime import datetime, timezone

from odoo import fields

from ....adapters.legacy_mapper import message_to_legacy_dict
from ....adapters.outlook_adapter import OutlookAdapter
from ....infrastructure.rendering.ui_formatting import (
    avatar_html,
    display_name_from_email,
)
from ....application.services.display_formatting import format_sender_display

# Import factory for client creation
from .client_factory import get_outlook_client

_logger = logging.getLogger(__name__)


def _graph_dt(dt):
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


def outlook_query_from_filters(
    env,
    sync_self,
    account=None,
    flt=None,
    text=None,
    partner_id=None,
    email_from=None,
):
    parts = []
    search_parts = []

    # Domain -> Filter logic
    if flt:
        if flt == "starred":
            parts.append("flag/flagStatus eq 'flagged'")
        elif flt == "read":
            parts.append("isRead eq true")
        elif flt == "unread":
            parts.append("isRead eq false")
        elif flt == "attachments":
            parts.append("hasAttachments eq true")

    if partner_id:
        Partner = env["res.partner"]
        p = Partner.browse(partner_id)
        if p.exists() and p.email:
            # For partner, we filter by sender OR recipient
            # Graph $search is better for "from or to or cc" logic than complex $filter
            # But let's try strict sender filter if implied context
            parts.append(f"from/emailAddress/address eq '{p.email}'")

    if email_from:
        parts.append(f"from/emailAddress/address eq '{email_from}'")

    # Text search integration
    if text:
        # escapes for KQL are minimal: " needs to be escaped
        safe_txt = text.replace('"', '\\"')
        search_parts.append(f'"{safe_txt}"')

    res = {}
    if parts:
        res["$filter"] = " and ".join(parts)
    if search_parts:
        res["$search"] = " AND ".join(search_parts)

    return res


def outlook_unread_counts(
    env, sync_self, sess, base_url, account, folder, flt, text, partner_id, email_from
):
    """
    Returns (unread_total, unread_filtered).
    unread_total is the folder's intrinsic unread count.
    unread_filtered is the count matching the current domain AND unread=true.
    """
    unread_total = 0
    unread_filtered = 0

    try:
        folder_id = outlook_resolve_folder_id(env, sess, base_url, folder)
    except Exception as e:
        _logger.warning("Outlook unread_counts: resolve folder failed: %s", e)
        return 0, 0

    try:
        url_folder = f"{base_url}/me/mailFolders/{folder_id}?$select=unreadItemCount"
        r = sess.get(url_folder, timeout=10)
        if r.status_code == 200:
            data = r.json()
            unread_total = int(data.get("unreadItemCount") or 0)
        else:
            _logger.warning(
                "Outlook unread_counts: folder GET %s -> %s",
                url_folder,
                r.status_code,
            )
    except Exception as e:
        _logger.warning("Outlook unread_counts: unread_total failed: %s", e)

    unread_filtered = unread_total

    try:
        qdict = outlook_query_from_filters(
            env,
            sync_self,
            account=account,
            flt=flt,
            text=text,
            partner_id=partner_id,
            email_from=email_from,
        )

        filter_expr = qdict.get("$filter") or ""
        if "isRead" not in filter_expr:
            filter_expr = (filter_expr + " and isRead eq false").strip(" and")

        search_q = qdict.get("$search")

        if not filter_expr and not search_q:
            return unread_total, unread_total

        url_count = f"{base_url}/me/mailFolders/{folder_id}/messages"

        params = {
            "$top": 1,
            "$count": "true",
        }
        headers = {
            "ConsistencyLevel": "eventual",
        }

        if filter_expr:
            params["$filter"] = filter_expr
        if search_q:
            params["$search"] = search_q

        r = sess.get(url_count, params=params, headers=headers, timeout=30)

        if r.status_code == 200:
            try:
                data = r.json() or {}
                cnt = data.get("@odata.count")
                if cnt is not None:
                    unread_filtered = int(cnt)
                else:
                    _logger.warning(
                        "Outlook unread_counts: no @odata.count in response: %r",
                        data,
                    )
            except Exception as e:
                _logger.warning(
                    "Outlook unread_counts: cannot parse count response (%s): %r",
                    e,
                    r.text,
                )
        else:
            _logger.warning(
                "Outlook unread_counts: $count failed (%s), fallback to total",
                r.status_code,
            )
            unread_filtered = unread_total

    except Exception as e:
        _logger.warning("Outlook unread_counts: filtered failed: %s", e)
        unread_filtered = unread_total

    return unread_total, unread_filtered


def outlook_resolve_folder_id(env, sess, base_url, folder):
    if not folder:
        return "inbox"

    if isinstance(folder, str):
        path = folder.strip()
    else:
        path = (folder.imap_name or folder.name or "").strip()
    if not path:
        return "inbox"

    pk = path.lower()
    WELL_KNOWN = {
        "inbox": "inbox",
        "sentitems": "sent",
        "drafts": "drafts",
        "deleteditems": "trash",
        "junkemail": "spam",
        "archive": "archive",
    }

    if pk in WELL_KNOWN:
        return WELL_KNOWN[pk]

    parts = [p.strip() for p in path.split("/") if p.strip()]
    if not parts:
        result = "inbox"
    else:
        url = f"{base_url}/me/mailFolders?$select=id,displayName,childFolderCount"
        current_id = None
        for part in parts:
            found = False
            while url:
                r = sess.get(url, timeout=30)
                r.raise_for_status()
                data = r.json()
                for item in data.get("value", []):
                    if (item.get("displayName") or "").strip().lower() == part.lower():
                        current_id = item["id"]
                        found = True
                        break
                if found:
                    break
                url = data.get("@odata.nextLink")
            if not found:
                current_id = "inbox"
                break
            url = f"{base_url}/me/mailFolders/{current_id}/childFolders?$select=id,displayName,childFolderCount"
        result = current_id or "inbox"

    return result


def outlook_list_message_ids(
    env, sync_self, sess, base_url, account, folder, qdict, offset, limit
):
    need = offset + limit
    got_ids = []
    seen_urls = set()
    params = {"$select": "id", "$top": "50"}
    headers = {}

    if qdict.get("$search"):
        headers["ConsistencyLevel"] = "eventual"
        params["$search"] = qdict["$search"]
    else:
        params["$orderby"] = "receivedDateTime desc"

    if qdict.get("$filter"):
        params["$filter"] = qdict["$filter"]

    if folder:
        fid = outlook_resolve_folder_id(env, sess, base_url, folder)
        url = f"{base_url}/me/mailFolders/{fid}/messages"
    else:
        url = f"{base_url}/me/messages"

    attempt = 0
    while len(got_ids) < need and attempt < 10:
        attempt += 1
        if url in seen_urls:
            _logger.warning(
                "Graph paging loop detected, stopping at attempt %s", attempt
            )
            break
        seen_urls.add(url)

        r = sess.get(url, params=params, headers=headers, timeout=30)
        if r.status_code >= 400:
            txt = r.text
            if "InefficientFilter" in txt and "$orderby" in (params or {}):
                _logger.warning("Graph: InefficientFilter → retry without $orderby")
                params.pop("$orderby", None)
                continue
            raise Exception(f"Outlook list error: {r.text}")

        data = r.json()
        ids = [m["id"] for m in data.get("value", [])]
        got_ids.extend(ids)

        next_url = data.get("@odata.nextLink")
        if not next_url or not ids:
            break
        url, params = next_url, None

    ids_page = got_ids[offset : offset + limit]
    return ids_page, len(got_ids)


def outlook_get_folder_name(env, sess, base_url, folder_id):
    url = f"{base_url}/me/mailFolders/{folder_id}?$select=displayName"
    r = sess.get(url, timeout=10)
    if r.status_code == 200:
        return (r.json().get("displayName") or "").strip()
    return ""


def outlook_fetch_meta_batch(
    env,
    sync_self,
    sess,
    base_url,
    account,
    folder,
    ids,
    partner_cache,
    update_cache=True,
):
    if not ids:
        return []

    fld = folder or False
    folder_name = (
        getattr(fld, "imap_name", None) or getattr(fld, "name", None) or "Inbox"
    )

    adapter = OutlookAdapter(sync_self)
    try:
        msgs = adapter.fetch_metadata_batch(
            sess, base_url, account.id, folder_name, ids
        )
    except Exception as e:
        _logger.debug("OutlookAdapter fetch_metadata_batch error: %s", e)
        return []

    recs = []
    for m in msgs:
        # Convert to legacy dict
        rec = message_to_legacy_dict(m)

        # Enrich with Partner info (Legacy behavior - preserve this separation)
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
        rec["is_read"] = m.is_read
        rec["is_starred"] = m.is_starred
        rec["has_attachments"] = m.has_attachments
        rec["to_display"] = m.to_display
        rec["cc_display"] = m.cc_display

        # Format date for UI
        if m.date:
            try:
                # Use env.context to get user timezone, or sync_self context
                dt_ctx = fields.Datetime.context_timestamp(sync_self, m.date)
                rec["formatted_date"] = dt_ctx.strftime("%d %b %Y %H:%M")
            except Exception:
                rec["formatted_date"] = ""
        else:
            rec["formatted_date"] = ""

        # Critical: Ensure account, backend type and folder ID are present for JS logic
        rec["account_id"] = [account.id, account.name]
        rec["backend_type"] = "outlook"
        rec["folder_id"] = fld.id if fld else False
        rec["conversation_id"] = m.thread_id

        recs.append(rec)

    return recs


def outlook_resolve_folder_ids(env, sync_self, names_or_ids, account):
    if not account or not account.id:
        _logger.error("[GRAPH] _outlook_resolve_folder_ids called with empty account")
        return {}

    sess, base = get_outlook_client(env, account)
    if not sess:
        return {}

    res = {}
    well_known = {
        "INBOX": f"{base}/me/mailFolders/inbox",
        "SENT": f"{base}/me/mailFolders/sentitems",
        "DRAFTS": f"{base}/me/mailFolders/drafts",
        "DELETED": f"{base}/me/mailFolders/deleteditems",
        "ARCHIVE": f"{base}/me/mailFolders/archive",
        "JUNK": f"{base}/me/mailFolders/junkemail",
    }

    for n in names_or_ids:
        key = (n or "").strip()
        up = key.upper()
        if up in well_known:
            try:
                r = sess.get(well_known[up], timeout=30)
                r.raise_for_status()
                res[n] = r.json().get("id") or n
            except Exception:
                res[n] = None
        else:
            res[n] = None

    pending = [n for n, fid in res.items() if not fid]
    if pending:
        url = f"{base}/me/mailFolders?$top=500&$select=id,displayName"
        while url and pending:
            try:
                r = sess.get(url, timeout=60)
                r.raise_for_status()
                data = r.json()
                by_name = {
                    (it.get("displayName") or "").strip().upper(): it.get("id")
                    for it in data.get("value", []) or []
                }
                for n in list(pending):
                    fid = by_name.get(n.strip().upper())
                    if fid:
                        res[n] = fid
                        pending.remove(n)
                url = data.get("@odata.nextLink")
            except Exception:
                break

        for n in pending:
            res[n] = n

    return res
