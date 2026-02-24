# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Email Utilities: Common helpers for header decoding, display formatting, and HTML processing.
"""

from email.header import decode_header
from email.utils import parseaddr

from odoo.tools import html2plaintext


def decode_header_value(header):
    """Decode standard email header."""
    if not header:
        return ""
    parts = []
    for decoded, charset in decode_header(header):
        if isinstance(decoded, bytes):
            if charset:
                try:
                    parts.append(decoded.decode(charset, errors="replace"))
                except LookupError:
                    parts.append(decoded.decode("utf-8", errors="replace"))
            else:
                parts.append(decoded.decode("utf-8", errors="replace"))
        else:
            parts.append(str(decoded))
    return "".join(parts)


def parse_sender_header(header):
    """Parse From header into (name, email)."""
    # Simple regex-based parsing to avoid heavy email.utils if not needed,
    # but email.utils.parseaddr is robust.
    # Attempting to replicate Odoo/Python standard behavior or extracted legacy logic.

    name, email = parseaddr(header)
    return header, name, email


def display_name_from_email(email):
    """Extract display name from email (e.g. 'foo' from 'foo@bar.com')."""
    if not email:
        return ""
    return email.split("@")[0].replace(".", " ").title()


def avatar_html(env, email, partner):
    """Generate avatar HTML."""
    # This requires env for rendering or URL generation if not just returning static HTML.
    # Legacy logic:
    # return f'<img src="/web/image?model=res.partner&id={partner.id}&field=avatar_128" />' etc.
    # Let's verify legacy implementation first.
    pass


def strip_html_to_text(html):
    """Strip HTML to plain text."""
    # Use Odoo's html2plaintext or equivalent

    return html2plaintext(html)


def norm_msgid(msgid):
    """Normalize Message-ID."""
    return (msgid or "").strip().strip("<>")
