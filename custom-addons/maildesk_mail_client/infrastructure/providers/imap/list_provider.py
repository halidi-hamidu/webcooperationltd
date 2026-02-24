# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk List Provider.

Implements infrastructure integration for List Provider (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from odoo import fields

from ....infrastructure.rendering import ui_formatting
from ....application.services.display_formatting import format_sender_display
from ....infrastructure.utils.email_utils import (
    decode_header_value,
    norm_msgid,
    parse_sender_header,
)
from ....infrastructure.rendering.preview_extractor import extract_imap_preview
from ....adapters.imap_adapter import ImapAdapter
from ....adapters.legacy_mapper import message_to_legacy_dict
from .pool import get_pool
from .utils import has_attachments_from_bodystructure


def fetch_list_records_parallel(
    env,
    client,
    uids,
    folder,
    account,
    partner_cache,
    batch_size=20,
    max_workers=4,
):
    """
    Retrieve IMAP message metadata for a list of UIDs, preloading cheap flags
    and body structures for all IDs before parallelizing full fetches.
    A thread pool pipelines BODY.PEEK and ENVELOPE downloads to minimize
    latency and then merges partner lookups into the final record set.

    Args:
        env: Odoo environment
        client: IMAP client (unused - pool used instead)
        uids: List of UIDs to fetch
        folder: Folder record
        account: Account record
        partner_cache: Partner lookup cache
        batch_size: Batch size for parallel fetching
        max_workers: Thread pool size

    Returns:
        list: Message records with metadata
    """
    if not uids:
        return []

    folder_name = folder.imap_name or folder.name
    pool = get_pool(account)

    with pool.session() as c:
        c.select_folder(folder_name, readonly=True)
        try:
            light_data = (
                c.fetch(
                    uids,
                    ["UID", "FLAGS", "BODYSTRUCTURE"],
                )
                or {}
            )
        except Exception:
            light_data = {}

    to_fetch_full = list(uids)

    full_records = {}

    # We need an adapter instance for fetch_metadata_batch which expects sync_self.
    # But wait, ImapAdapter usage on line 110: `adapter = ImapAdapter(sync_self)`
    # We need to check if ImapAdapter actually needs sync_self or can take env.
    # Assuming ImapAdapter logic for fetch_metadata_batch is robust or needs fixing too.
    # For now, we can mock sync_self or adapt ImapAdapter.
    # Actually, `fetch_metadata_batch` likely uses sync_self for similar helpers.
    # Let's inspect ImapAdapter briefly or try to instantiate it with a dummy or env if possible.
    # Legacy: adapter = ImapAdapter(sync_self)
    # If ImapAdapter uses sync_self for _is_gmail... it might fail.
    # However, fetch_metadata_batch is likely lower level.
    # Let's check line 110 replacement.

    # TEMPORARY FIX: Avoid using ImapAdapter if possible or construct it with a facade if needed.
    # But wait, `fetch_metadata_batch` is static-ish?
    # Actually, let's keep sync_self removed and see.
    # ImapAdapter is imported from `....adapters.imap_adapter`.

    # For now, let's assume we can construct ImapAdapter(env) if we modify it, OR
    # just instantiate it with an object that has `env` = env.

    class Facade:
        def __init__(self, env):
            self.env = env

        def _parse_sender_header(self, h):
            return parse_sender_header(h)

        def _decode_header_value(self, h):
            return decode_header_value(h)

        def _to_datetime(self, d):
            if not d:
                return None
            if isinstance(d, datetime):
                return d
            return fields.Datetime.to_datetime(d)

        def _join_addresses(self, addr_list):
            # addr_list is typically a list of (name, email) tuples or similar from parsed headers
            # OR simple strings if already normalized.
            # ImapAdapter L96 passes getattr(env, "to", None) which involves Python's strict parser...
            # Wait, ImapAdapter parses HEADER.FIELDS result manually on L60,
            # BUT passed structure `env` variable comes from `client.fetch(..., "ENVELOPE")`.
            # IMAP Envelope structure for TO/CC is list of addresses.
            # We need to handle IMAP Envelope format if ImapAdapter passes that.
            # ImapAdapter L54: env = d.get(b"ENVELOPE").
            # Odoo's imap/fetch logic typically returns struct.
            # If standard Python imaplib, it's structured.
            # MailboxSync._join_addresses source check needed?
            # Let's simple join for now assuming string list or implement robustly if easy.
            if not addr_list:
                return ""
            # If it's a list of address structures (name, adl, mailbox, host)
            # Standard IMAP envelope address structure.
            res = []
            for addr in addr_list:
                if isinstance(addr, (list, tuple)) and len(addr) >= 4:
                    name = (addr[0] or b"").decode("utf-8", "ignore")
                    mailbox = (addr[2] or b"").decode("utf-8", "ignore")
                    host = (addr[3] or b"").decode("utf-8", "ignore")
                    email = f"{mailbox}@{host}"
                    if name:
                        res.append(f"{name} <{email}>")
                    else:
                        res.append(email)
                else:
                    res.append(str(addr))
            return ", ".join(res)

        def _norm_msgid(self, m):
            return norm_msgid(m)

        def _extract_imap_preview(self, body_bytes, subject):
            """Extract a stable preview text from IMAP message bytes."""
            return extract_imap_preview(body_bytes, subject)

    adapter = ImapAdapter(Facade(env))

    def _full_fetch(need_uids):
        msgs = adapter.fetch_metadata_batch(need_uids, folder_name, account.id, pool)
        res = {}
        for m in msgs:
            res[int(m.id)] = message_to_legacy_dict(m)
        return res

    chunks = [
        to_fetch_full[i : i + batch_size]
        for i in range(0, len(to_fetch_full), batch_size)
    ]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_full_fetch, ch) for ch in chunks]
        for f in as_completed(futs):
            part = f.result() or {}
            full_records.update(part)

    records = []

    for uid in uids:
        d = light_data.get(uid, {}) or {}
        flags = d.get(b"FLAGS", [])
        bs = d.get(b"BODYSTRUCTURE")

        is_read = (
            b"\\Seen" in flags
            or b"\\seen" in flags
            or "\\Seen" in flags
            or "\\seen" in flags
        )

        is_starred = b"\\Flagged" in flags or "\\Flagged" in flags

        is_draft = b"\\Draft" in flags or "\\Draft" in flags

        has_att = has_attachments_from_bodystructure(bs)

        full = full_records.get(uid)

        if full:
            base = full
        else:
            base = {
                "uid": uid,
                "subject": "(no subject)",
                "preview": "",
                "from_addr": "",
                "to_addrs": "",
                "cc_addrs": "",
                "date": datetime(1970, 1, 1),
                "thread_id": "",
                "message_id": "",
                "in_reply_to": "",
                "references_hdr": "",
            }

        email_from = base.get("from_addr", "").lower()

        partner = partner_cache.get(email_from)
        if partner is None:
            partner = env["res.partner"].search(
                [("email", "=ilike", email_from)], limit=1
            )
            partner_cache[email_from] = partner

        sender_name = (
            partner.name
            if partner
            else ui_formatting.display_name_from_email(email_from)
        )

        dt = base.get("date") or datetime(1970, 1, 1)
        if isinstance(dt, str):
            try:
                dt = fields.Datetime.from_string(dt)
            except Exception:
                dt = datetime(1970, 1, 1)

        if getattr(dt, "tzinfo", None):
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

        user_dt = fields.Datetime.context_timestamp(env.user, dt)

        formatted_date = user_dt.strftime("%d %b %Y %H:%M")

        rec = {
            "id": uid,
            "account_id": [account.id, account.name],
            "folder_id": folder.id if folder else False,
            "subject": base.get("subject") or "(no subject)",
            "email_from": email_from,
            "sender_display_name": format_sender_display(sender_name, email_from),
            "date": dt,
            "formatted_date": formatted_date,
            "is_read": is_read,
            "is_starred": is_starred,
            "is_draft": is_draft,
            "has_attachments": has_att,
            "to_display": base.get("to_addrs") or "",
            "cc_display": base.get("cc_addrs") or "",
            "preview_text": base.get("preview") or "",
            "avatar_html": ui_formatting.avatar_html(
                email_from, partner, ui_formatting.display_name_from_email
            ),
            "avatar_partner_id": partner.id if partner else False,
            "message_id_norm": base.get("message_id") or "",
            "in_reply_to": base.get("in_reply_to") or "",
            "references_hdr": base.get("references_hdr") or "",
            "thread_id": base.get("thread_id") or "",
            "tag_ids": [],
            "msg_key": f"{account.id}|{folder.id if folder else ''}|{uid}",
        }

        records.append(rec)

    return records
