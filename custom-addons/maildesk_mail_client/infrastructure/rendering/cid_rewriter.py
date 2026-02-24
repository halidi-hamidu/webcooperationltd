# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Infrastructure: CID (Content-ID) Rewriting for RECEIVED emails

Replaces CID references in HTML with access-tokened `/web/image/...` URLs so the
HTML is safe to cache and display without client-side fixups.

For SENT emails with inline images, see `mime_builder.py` which handles
CID → Content-ID header mapping at send-time.

Follows Odoo mail_thread.py pattern (lines 2436-2451):
- Only replace if attachment_id AND token exist
- Leave unresolved CIDs unchanged (never empty src)
- Use lxml for parsing
"""

import logging
from typing import Any, Dict, List, Optional

from urllib.parse import urlsplit

import lxml.html

_logger = logging.getLogger(__name__)


def _normalize_base_url(base_url: Optional[str]) -> str:
    base_url = (base_url or "").strip()
    if not base_url:
        return ""
    try:
        parts = urlsplit(base_url)
    except Exception:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return base_url.rstrip("/")


def replace_cid_src(
    body_html: str,
    attachments: List[Dict[str, Any]],
    *,
    base_url: Optional[str] = None,
) -> str:
    """
    Replace CID references in HTML img src with attachment URLs.

    Follows Odoo mail_thread.py:2436-2451 pattern exactly:
    - Build CID → (attachment_id, token) mapping
    - Replace src ONLY if BOTH attachment_id AND token exist
    - Leave unresolved CIDs unchanged (src="cid:..." stays intact)
    - This guarantees <img src=""> NEVER happens

    Args:
        body_html: HTML body content
        attachments: List of attachment dicts with:
            - id: attachment ID
            - access_token: access token string
            - content_id or contentId: Content-ID header value

    Returns:
        str: HTML with replaced CID references
    """
    if not body_html or not attachments:
        return body_html

    # Build CID → (id, token) mapping (Odoo pattern: lines 2427-2432)
    cid_mapping: Dict[str, tuple] = {}
    for att in attachments:
        # Extract content_id (handle multiple naming conventions)
        raw_cid = att.get("content_id") or att.get("contentId") or att.get("cid") or ""
        if not raw_cid:
            continue

        # Normalize: strip angle brackets and whitespace
        cid = raw_cid.strip().strip("<>").strip()
        if not cid:
            continue

        att_id = att.get("id")
        token = att.get("access_token")

        # Odoo pattern: only add to mapping if BOTH exist
        if att_id and token:
            cid_mapping[cid] = (att_id, token)
            # Also map base (before @) for flexibility
            if "@" in cid:
                base = cid.split("@", 1)[0]
                cid_mapping[base] = (att_id, token)

    if not cid_mapping:
        return body_html

    # Parse HTML with lxml (Odoo uses lxml, not BeautifulSoup)
    try:
        root = lxml.html.fromstring(body_html)
    except Exception as e:
        _logger.warning(f"[CID Rewriter] Failed to parse HTML: {e}")
        return body_html

    def _resolve_cid_url(cid_ref: str) -> str:
        cid_ref = (cid_ref or "").strip()
        if not cid_ref:
            return ""
        cid_raw = cid_ref.strip()
        cid_clean = cid_raw.strip("<>").strip()
        att_id, token = cid_mapping.get(cid_raw, (False, False))
        if not att_id or not token:
            att_id, token = cid_mapping.get(cid_clean, (False, False))
        if not att_id or not token:
            if "@" in cid_clean:
                base_part = cid_clean.split("@", 1)[0]
                att_id, token = cid_mapping.get(base_part, (False, False))
        if not att_id or not token:
            return ""
        route = f"/web/image/{att_id}?access_token={token}"
        return f"{_base}{route}" if _base else route

    modified = False
    _base = _normalize_base_url(base_url)

    # Received emails can reference CIDs in non-<img> elements (e.g. VML: <v:imagedata src="cid:...">).
    # We rewrite any attribute value that is a cid: URL; unresolved CIDs are left intact (scrubbed later).
    for node in root.iter():
        for attr in ("src", "href", "xlink:href", "data", "background"):
            val = node.get(attr, "")
            if not isinstance(val, str) or not val.startswith("cid:"):
                continue
            cid_part = val.split("cid:", 1)[1].strip()
            resolved = _resolve_cid_url(cid_part)
            if resolved:
                node.set(attr, resolved)
                modified = True

        srcset = node.get("srcset", "")
        if isinstance(srcset, str) and "cid:" in srcset:
            new_parts = []
            changed = False
            for part in srcset.split(","):
                part = part.strip()
                if not part:
                    continue
                url, *rest = part.split(" ", 1)
                if url.startswith("cid:"):
                    resolved = _resolve_cid_url(url.split("cid:", 1)[1])
                    if resolved:
                        url = resolved
                        changed = True
                new_parts.append(" ".join([url] + rest).strip())
            if changed:
                node.set("srcset", ", ".join([p for p in new_parts if p]))
                modified = True

    if modified:
        return lxml.html.tostring(root, encoding="unicode")
    return body_html
