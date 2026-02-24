# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Search Criteria Builders

Functions for constructing and executing IMAP searches.
"""

import re


def criteria_key(criteria):
    """
    Flatten an IMAP search criteria structure into an uppercase string key.
    Useful for caching results keyed by logical criteria regardless of list nesting.
    """

    def flat(x):
        if isinstance(x, (list, tuple)):
            return "(" + " ".join(flat(i) for i in x) + ")"
        return str(x)

    return flat(criteria).upper()


def build_search_criteria(
    env, account=None, flt=None, text=None, partner_id=None, email_from=None
):
    """
    Build IMAP search criteria from filter parameters.

    Args:
        env: Odoo environment (for partner lookups)
        account: Account record (for sender filtering)
        flt: Filter type ('unread', 'starred', 'incoming', 'outgoing')
        text: Full-text search string
        partner_id: Partner ID to filter by email
        email_from: Direct email filter

    Returns:
        list: IMAP search criteria
    """
    criteria = ["ALL"]
    sender = (account.email or "").lower() if account else ""
    if flt == "unread":
        criteria.append("UNSEEN")
    elif flt == "starred":
        criteria.append("FLAGGED")
    elif flt == "incoming":
        if sender:
            criteria.extend(["NOT", ["FROM", sender]])
    elif flt == "outgoing":
        if sender:
            criteria.extend(["FROM", sender])
    if partner_id and not email_from:
        partner = env["res.partner"].browse(partner_id)
        if partner and partner.email:
            email_from = partner.email
    if email_from:
        criteria.extend(["FROM", (email_from or "").lower()])
    if text:
        s = re.sub(r"\s+", " ", text.strip())
        if s:
            criteria.extend(["TEXT", s])
    return criteria


def fast_search_uids(
    client, env, folder_name, criteria, offset, limit, is_all, account
):
    """
    Search IMAP for message UIDs with heuristics that limit server load.
    Uses a sliding UID window near UIDNEXT and applies UTF-8 searches when supported.
    """
    res = client.select_folder(folder_name, readonly=True)
    uidnext = int(res.get(b"UIDNEXT") or res.get("UIDNEXT") or 1)

    base = offset + limit * 3
    window = 5000 if not is_all else max(400, base)
    start = max(1, uidnext - window)

    crit = [c for c in criteria if c != "ALL"] + ["UID", f"{start}:*"]

    def _needs_charset(cs):
        flat = " ".join(map(str, cs)).upper()
        return any(
            k in flat
            for k in (
                "TEXT ",
                " BODY ",
                " SUBJECT ",
                " FROM ",
                " TO ",
                " CC ",
                " BCC ",
            )
        )

    try:
        caps = client.capabilities() or []
        utf8_ok = (b"UTF8=ACCEPT" in caps) or ("UTF8=ACCEPT" in caps)
    except Exception:
        utf8_ok = False

    charset = "UTF-8" if (utf8_ok and _needs_charset(crit)) else None

    uids = client.search(crit, charset=charset) or []
    u_sorted = sorted([int(u) for u in uids], reverse=True)

    return u_sorted[offset : offset + limit], len(u_sorted)
