# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Text helpers for stable email previews.

These helpers are intentionally free of OWL/Odoo concerns and can be reused
whenever the UI needs a short, stable snippet of text extracted from a larger
blob.
"""

from __future__ import annotations

import re

_REPLY_MARKERS = (
    re.compile(r"(?i)^on .+wrote:"),
    re.compile(r"(?i)^am .+schrieb"),
)

_BASE64_TEXT_RE = re.compile(r"^[A-Za-z0-9+/=\s]+$")


def looks_like_base64(text: str) -> bool:
    """
    Detect base64-like payloads to avoid showing unreadable previews.

    This is heuristic and intentionally conservative.
    """
    stripped = (text or "").strip()
    if len(stripped) < 80:
        return False
    if not _BASE64_TEXT_RE.match(stripped[:400]):
        return False
    compact = re.sub(r"\s+", "", stripped)
    return len(compact) >= 80 and re.fullmatch(r"[A-Za-z0-9+/=]+", compact) is not None


def looks_like_mime_noise(line: str) -> bool:
    """Return True for header-ish / MIME boundary lines that should not enter previews."""
    low = (line or "").lstrip().lower()
    if not low:
        return False
    return bool(
        low.startswith("--")
        or low.startswith("content-type:")
        or low.startswith("content-transfer-encoding:")
        or low.startswith("mime-version:")
        or low.startswith("_part_")
        or low.startswith("=_part_")
    )


def clean_preview_text(text: str) -> str:
    """
    Normalize extracted text into a short, readable single-line snippet.

    - Skips quoted lines and common reply markers.
    - Skips MIME noise (headers/boundaries).
    - Collapses whitespace.
    """
    lines = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(">"):
            continue
        if looks_like_mime_noise(s):
            continue
        if any(pat.match(s) for pat in _REPLY_MARKERS):
            break
        lines.append(s)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()
