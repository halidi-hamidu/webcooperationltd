# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Message Enricher - Enrich message records with tags and partner metadata.

Provides enrichment functions for adding tag information and partner
metadata to message dictionaries.
"""

from ...domain.services.normalization import norm_msgid
from ..rendering.ui_formatting import avatar_html, display_name_from_email


def enrich_with_tags(account, rec, env):
    """
    Enrich message record with tag information.

    Args:
        account: Mailbox account record
        rec: Message dictionary
        env: Odoo environment

    Returns:
        Enriched message dictionary with tag_ids
    """
    if not rec:
        return rec

    if rec.get("is_local_draft"):
        return rec

    index_id = rec.get("index_id")
    if index_id is None and "uid" in rec:
        index_id = rec.get("id")
    if isinstance(index_id, str):
        raise ValueError(
            "BUG: string UID passed where message_index.id (int) is expected"
        )
    if isinstance(index_id, bool) or not isinstance(index_id, int):
        index_id = None

    if index_id:
        try:
            MessageIndex = env["maildesk.message_index"].sudo()
            index_rec = MessageIndex.browse(index_id)

            if index_rec.exists() and index_rec.tag_ids:
                # Format tags as objects with id, name, color
                rec["tag_ids"] = [
                    {"id": t.id, "name": t.name, "color": t.color}
                    for t in index_rec.tag_ids
                ]
                return rec
        except Exception:
            pass

    # No tags found in SSOT - return empty
    rec["tag_ids"] = []
    return rec


def enrich_with_partner_meta(rec, env):
    """
    Enrich message record with partner metadata.

    Args:
        rec: Message dictionary
        env: Odoo environment

    Returns:
        Enriched message dictionary with partner info
    """
    email = (rec.get("email_from") or "").strip().lower()
    partner = env["res.partner"].search([("email", "=ilike", email)], limit=1)

    rec["avatar_partner_id"] = partner.id if partner else False
    rec["partner_trusted"] = bool(partner.trusted_partner) if partner else False

    rec["trusted_by_user_id"] = (
        partner.trusted_by_user_id.id
        if partner and partner.trusted_by_user_id
        else False
    )

    rec["avatar_html"] = avatar_html(email, partner, display_name_from_email)

    rec["message_id_norm"] = norm_msgid(rec.get("message_id") or "")
    rec["in_reply_to"] = rec.get("in_reply_to") or ""
    rec["in_reply_to_norm"] = norm_msgid(rec["in_reply_to"])

    return rec
