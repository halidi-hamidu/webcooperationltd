# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Infrastructure: HTML Sanitization Utilities

Functions for sanitizing and processing HTML email content.
"""

import re
from html import unescape as html_unescape

from bs4 import BeautifulSoup


def sanitize_email_html(html):
    """
    Sanitize HTML email content by removing scripts, iframes, and dangerous attributes.
    """
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "iframe", "object", "embed"]):
        tag.decompose()
    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)
        for attr_name in list(attrs.keys()):
            if attr_name.lower().startswith("on"):
                tag.attrs.pop(attr_name, None)
        for key in ("href", "src"):
            if key in tag.attrs:
                val = tag.attrs.get(key) or ""
                if isinstance(val, str) and val.strip().lower().startswith(
                    "javascript:"
                ):
                    tag.attrs[key] = "#"
        style_val = tag.attrs.get("style")
        if isinstance(style_val, str):
            low = style_val.lower()
            if "expression(" in low or "javascript:" in low:
                tag.attrs.pop("style", None)
        if tag.name == "a":
            tag.attrs["target"] = "_blank"
            rel = tag.attrs.get("rel")
            if isinstance(rel, list):
                rel_tokens = set(rel)
            elif isinstance(rel, str):
                rel_tokens = set(rel.split())
            else:
                rel_tokens = set()
            rel_tokens.update(["noopener", "noreferrer"])
            tag.attrs["rel"] = " ".join(sorted(rel_tokens))
    return str(soup)


def strip_html_to_text(html):
    """
    Strip HTML tags and convert to plain text.
    """
    text = html_unescape(html or "")
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n", text)
    text = re.sub(r"(?is)<.*?>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()
