# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Domain Services: Email Normalization Utilities

Pure functions for normalizing email headers, dates, and identifiers.
No Odoo dependencies - these are protocol-level utilities.
"""

import re
from datetime import date, datetime
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from odoo import fields
from odoo.tools.mail import decode_message_header, email_split_tuples


def safe_dt(rec):
    """
    Convert the "date" field of a record to a datetime object, defaulting to
    the Unix epoch when parsing fails. This guards downstream comparisons and
    ordering logic against malformed strings or unexpected types.
    """
    d = rec.get("date")
    if isinstance(d, datetime):
        return d
    try:
        dt = fields.Datetime.to_datetime(d)
        return dt if dt else datetime(1970, 1, 1)
    except Exception:
        return datetime(1970, 1, 1)


def json_safe(value):
    """
    Recursively transform date and datetime values into Odoo string
    representations so structures can be serialized to JSON. Nested lists, sets,
    tuples, and dictionaries are traversed to ensure all temporal objects are
    converted while preserving the original container shape.
    """
    if isinstance(value, datetime):
        return fields.Datetime.to_string(value)
    if isinstance(value, date):
        return fields.Date.to_string(value)
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    return value


def to_datetime(value):
    """Convert email date value to datetime object."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "ignore")
    if isinstance(value, str):
        try:
            dt = parsedate_to_datetime(value)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except Exception:
            return fields.Datetime.now()
    return fields.Datetime.now()


def norm_msgid(val):
    """Normalize message ID to canonical form."""
    if not val:
        return ""
    if isinstance(val, (list, tuple)):
        val = " ".join([str(v or "") for v in val])
    s = str(val).strip()
    m = re.search(r"<([^>]+)>", s)
    if m:
        s = m.group(1)
    return s.strip().lower()


def msgid_header(val: str) -> str:
    """
    Normalize a Message-ID-like value into RFC 5322 header form: `<...>`.

    This is safe to use for:
    - `Message-ID`
    - `In-Reply-To`
    - entries inside `References`
    """
    inner = norm_msgid(val)
    return f"<{inner}>" if inner else ""


def parse_msgid_list(value: str):
    """
    Parse `References`-like header values into a de-duplicated list of `<...>` tokens.
    Preserves order (first occurrence wins).
    """
    if not value:
        return []

    s = str(value or "").strip()
    # Prefer the RFC form first: <id1> <id2> ...
    tokens = re.findall(r"<([^>]+)>", s)
    if not tokens:
        # Fallback: some providers send bare IDs or comma-separated junk.
        tokens = [t for t in re.split(r"[\s,]+", s) if t]

    out = []
    seen = set()
    for t in tokens:
        h = msgid_header(t)
        if h and h not in seen:
            out.append(h)
            seen.add(h)
    return out


def build_references_header(existing_references: str, in_reply_to: str) -> str:
    """
    Build a `References` header value from an existing chain plus a parent ID.

    RFC 5322 threading conventions:
    - `In-Reply-To`: parent Message-ID only
    - `References`: full ancestor chain (parent's References + parent Message-ID)
    """
    refs = parse_msgid_list(existing_references)
    parent = msgid_header(in_reply_to)
    if parent and parent not in refs:
        refs.append(parent)
    return " ".join(refs)


def decode_header_value(value):
    """Decode RFC 2047 encoded email headers."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8", "ignore")
        except Exception:
            value = value.decode("latin-1", "ignore")
    try:
        return str(make_header(decode_header(value))) or ""
    except Exception:
        msg = EmailMessage()
        msg["X"] = value
        return decode_message_header(msg, "X") or value


def parse_sender_header(header_bytes, display_name_extractor):
    """
    Parse sender header into formatted address, display name, and email.

    Args:
        header_bytes: Raw header value
        display_name_extractor: Function to extract display name from email

    Returns:
        tuple: (formatted_address, display_name, email)
    """
    header_val = (
        header_bytes.decode("utf-8", "ignore")
        if isinstance(header_bytes, (bytes, bytearray))
        else (header_bytes or "")
    )
    msg = EmailMessage()
    msg["From"] = header_val

    decoded = decode_message_header(msg, "From") or header_val
    pairs = email_split_tuples(decoded)

    if pairs:
        name, email = pairs[0]
        name = (name or "").strip()
        email = (email or "").lower()
        formatted = f"{name} <{email}>" if name else email
        return formatted, (name or email), email

    m = re.search(r"<([^>]+)>", decoded)
    if m:
        email = (m.group(1) or "").strip().lower()
        name = (decoded[: m.start()] or "").strip()
        formatted = f"{name} <{email}>" if name else email
        return formatted, (name or email), email

    email = decoded.strip().lower()
    return email, display_name_extractor(decoded), email


def join_addresses(lst, addr_to_email_func):
    """
    Render a list of parsed address objects into a comma-separated header string.
    Skips entries without valid email parts to keep output consistent with RFC formatting expectations.

    Args:
        lst: List of address objects
        addr_to_email_func: Function to extract email from address object
    """
    out = []
    for p in lst or []:
        name = (
            (p.name or "").decode()
            if isinstance(getattr(p, "name", None), (bytes, bytearray))
            else (p.name or "")
        )
        email = addr_to_email_func(p)
        if not email:
            continue
        out.append(f"{name} <{email}>" if name else email)
    return ", ".join(out)


def addr_to_email(addr_obj):
    """Extract email address from address object."""
    if (
        not addr_obj
        or not getattr(addr_obj, "mailbox", None)
        or not getattr(addr_obj, "host", None)
    ):
        return ""
    mailbox = (
        addr_obj.mailbox.decode()
        if isinstance(addr_obj.mailbox, (bytes, bytearray))
        else addr_obj.mailbox
    )
    host = (
        addr_obj.host.decode()
        if isinstance(addr_obj.host, (bytes, bytearray))
        else addr_obj.host
    )
    return f"{mailbox}@{host}".lower()
