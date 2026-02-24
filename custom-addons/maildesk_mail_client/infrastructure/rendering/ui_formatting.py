# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Infrastructure: UI Formatting Utilities

Functions for generating avatar HTML, initials, and display names.
"""

import hashlib
import re

from markupsafe import Markup


def hsl(seed):
    """
    Generate a deterministic HSL color string from the provided seed text by
    hashing it with MD5 and mapping the digest to a hue. This is used for
    consistent color assignments where the same input should always yield the
    same visual marker.
    """
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 360
    return f"hsl({h}, 70%, 50%)"


def avatar_initials(display_name):
    """
    Extract initials from a display name for avatar rendering.

    Args:
        display_name: Name to extract initials from

    Returns:
        str: Up to 2 initials or "?"
    """
    name = (display_name or "").strip()
    if not name:
        return "?"

    parts = [p for p in re.split(r"\s+", name) if p]

    letters = []
    for part in parts:
        for ch in part:
            if ch.isalpha():
                letters.append(ch.upper())
                break
            if ch.isdigit() and not letters:
                letters.append(ch)
                break
        if len(letters) == 2:
            break

    if not letters:
        return "?"

    return "".join(letters)


def avatar_html(email_from, partner, display_name_extractor):
    """
    Generate avatar HTML for email sender.

    Args:
        email_from: Email address
        partner: Partner record with avatar_128 and name
        display_name_extractor: Function to extract display name from email

    Returns:
        Markup: HTML for avatar (image or initials circle)
    """
    if partner and partner.avatar_128:
        display_name = (partner.name or "").strip() or display_name_extractor(
            email_from
        )
        display_name = (display_name or "").strip()
        unique = ""
        if partner.write_date:
            unique = f"?unique={str(partner.write_date).replace(' ', '').replace('-', '').replace(':', '')}"

        return Markup(
            f'<img src="/web/image/res.partner/{partner.id}/avatar_128{unique}" '
            f'class="rounded-circle sender-icon" width="42" height="42" '
            f'alt="{Markup.escape(display_name) or "Avatar"}"/>'
        )

    display_name = None
    if partner and partner.name:
        display_name = partner.name
    else:
        display_name = display_name_extractor(email_from)

    display_name = (display_name or "").strip()

    if not display_name or not re.search(r"\w", display_name):
        display_name = (email_from or "").strip()

    initials = avatar_initials(display_name)

    seed = None
    if partner:
        seed = (partner.name or "").strip() or f"partner:{partner.id}"
    if not seed:
        seed = display_name or (email_from or "x")

    bg = hsl(seed.lower())

    return Markup(
        '<div class="rounded-circle d-flex align-items-center justify-content-center '
        'sender-icon" '
        f'style="background:{bg};color:#fff;width:42px;height:42px;'
        'font-weight:700;font-size:16px;">'
        f"{Markup.escape(initials)}"
        "</div>"
    )


def display_name_from_email(value):
    """
    Extract display name from email address.

    Args:
        value: Email address or "Name <email>" format

    Returns:
        str: Display name
    """
    value = value or ""
    m = re.match(r"^(.*?)(<.*>)$", value)
    if m:
        return (m.group(1) or "").strip()
    if "@" in value:
        return value.split("@")[0].replace(".", " ").replace("_", " ").title()
    return value
