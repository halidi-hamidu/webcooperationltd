# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Message display normalization for RECEIVED emails.

Goal: FETCH ONCE → NORMALIZE ONCE → CACHE FINAL → DISPLAY.

This service produces the *final* body HTML that is safe to cache in
`maildesk.ui_cache`:
- no `cid:` references
- inline images resolved to `/web/image/...` (optionally absolute via base URL)
- deterministic sanitization and body_text extraction
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple

import lxml.html

_logger = logging.getLogger(__name__)


class MessageDisplayNormalizerDeps(Protocol):
    def base_url(self) -> str: ...
    def sanitize_email_html(self, html: str) -> str: ...
    def strip_html_to_text(self, html: str) -> str: ...
    def replace_cid_src(
        self,
        html: str,
        attachments: List[Dict[str, Any]],
        base_url: Optional[str] = None,
    ) -> str: ...

    def materialize_inline_attachments(
        self,
        *,
        provider: str,
        account: Any,
        folder: Any,
        uid: str,
        attachments: List[Dict[str, Any]],
        cache_key: int,
        needed_cids: Set[str],
    ) -> List[Dict[str, Any]]: ...


@dataclass(frozen=True)
class NormalizedBody:
    body_html: str
    body_text: str
    attachments: List[Dict[str, Any]]


def _cid_variants(cid: str) -> Set[str]:
    cid = (cid or "").strip().strip("<>").strip()
    if not cid:
        return set()
    out = {cid}
    if "@" in cid:
        out.add(cid.split("@", 1)[0])
    return out


def _extract_needed_cids(body_html: str) -> Set[str]:
    if not body_html:
        return set()
    try:
        root = lxml.html.fromstring(body_html)
    except Exception:
        return set(
            re.findall(r"cid:([^\s\"'>]+)", body_html or "", flags=re.IGNORECASE)
        )

    needed: Set[str] = set()
    for node in root.iter():
        for attr in ("src", "href", "xlink:href", "data", "background"):
            val = (node.get(attr) or "").strip()
            if val.lower().startswith("cid:"):
                needed |= _cid_variants(val.split(":", 1)[1])

        srcset = (node.get("srcset") or "").strip()
        if srcset and "cid:" in srcset.lower():
            for part in srcset.split(","):
                cand = (part.strip().split(" ", 1)[0] or "").strip()
                if cand.lower().startswith("cid:"):
                    needed |= _cid_variants(cand.split(":", 1)[1])

        style = (node.get("style") or "").strip()
        if style and "cid:" in style.lower():
            for m in re.findall(r"(?i)url\(\s*cid:([^)]+)\)", style):
                needed |= _cid_variants(m)
    return {c for c in needed if c}


def _scrub_remaining_cid_references(body_html: str) -> Tuple[str, bool]:
    if not body_html or "cid:" not in (body_html.lower()):
        return body_html, False
    try:
        root = lxml.html.fromstring(body_html)
    except Exception:
        scrubbed = re.sub(r"(?i)url\(\s*cid:[^)]+\)", "", body_html)
        scrubbed = re.sub(r"cid:[^\s\"'>]+", "", scrubbed, flags=re.IGNORECASE)
        return scrubbed, scrubbed != body_html

    modified = False
    nodes_to_drop: List[Any] = []
    for node in root.iter():
        for attr, val in list((node.attrib or {}).items()):
            if not isinstance(val, str) or "cid:" not in val.lower():
                continue

            low = val.lower().strip()
            if low.startswith("cid:"):
                if node.tag.lower() in {
                    "img",
                    "source",
                    "video",
                    "audio",
                    "object",
                    "embed",
                } or attr in {"src", "data", "background"}:
                    nodes_to_drop.append(node)
                    modified = True
                    break
                node.attrib.pop(attr, None)
                modified = True
                continue

            scrubbed_val = re.sub(r"(?i)url\(\s*cid:[^)]+\)", "", val)
            scrubbed_val = re.sub(
                r"cid:[^\s\"'>]+", "", scrubbed_val, flags=re.IGNORECASE
            )
            if scrubbed_val != val:
                if scrubbed_val:
                    node.set(attr, scrubbed_val)
                else:
                    node.attrib.pop(attr, None)
                modified = True

        srcset = node.get("srcset", "")
        if isinstance(srcset, str) and "cid:" in srcset.lower():
            new_parts: List[str] = []
            for part in srcset.split(","):
                part = part.strip()
                if not part:
                    continue
                url, *rest = part.split(" ", 1)
                if url.lower().startswith("cid:"):
                    modified = True
                    continue
                scrubbed_url = re.sub(r"(?i)url\(\s*cid:[^)]+\)", "", url)
                scrubbed_url = re.sub(
                    r"cid:[^\s\"'>]+", "", scrubbed_url, flags=re.IGNORECASE
                ).strip()
                if not scrubbed_url:
                    modified = True
                    continue
                new_parts.append(" ".join([scrubbed_url] + rest).strip())
            if new_parts:
                node.set("srcset", ", ".join([p for p in new_parts if p]))
            else:
                node.attrib.pop("srcset", None)
                modified = True
                if node.tag.lower() in {"img", "source"}:
                    nodes_to_drop.append(node)

    for node in nodes_to_drop:
        node.drop_tree()

    return (
        (lxml.html.tostring(root, encoding="unicode"), True)
        if modified
        else (body_html, False)
    )


def _absolutize_web_image_routes(body_html: str, base_url: str) -> str:
    base_url = (base_url or "").strip().rstrip("/")
    if not body_html or not base_url:
        return body_html

    try:
        root = lxml.html.fromstring(body_html)
    except Exception:
        return re.sub(
            r"(?i)([\"\'])/web/image/",
            r"\1" + base_url + "/web/image/",
            body_html,
        )

    modified = False
    for node in root.iter():
        for attr, val in list((node.attrib or {}).items()):
            if not isinstance(val, str):
                continue
            if val.startswith("/web/image/"):
                node.set(attr, base_url + val)
                modified = True
            if "url(/web/image/" in val:
                node.set(
                    attr, val.replace("url(/web/image/", f"url({base_url}/web/image/")
                )
                modified = True

        srcset = node.get("srcset", "")
        if isinstance(srcset, str) and "/web/image/" in srcset:
            new_parts = []
            changed = False
            for part in srcset.split(","):
                part = part.strip()
                if not part:
                    continue
                url, *rest = part.split(" ", 1)
                if url.startswith("/web/image/"):
                    url = base_url + url
                    changed = True
                new_parts.append(" ".join([url] + rest).strip())
            if changed:
                node.set("srcset", ", ".join([p for p in new_parts if p]))
                modified = True

    return lxml.html.tostring(root, encoding="unicode") if modified else body_html


def normalize_for_ui_cache(
    deps: MessageDisplayNormalizerDeps,
    *,
    provider: str,
    account: Any,
    folder: Any,
    uid: str,
    cache_key: int,
    body_html: str,
    body_text: Optional[str],
    attachments: List[Dict[str, Any]],
) -> NormalizedBody:
    raw_html = body_html or ""
    raw_text = (body_text or "").strip() if body_text else ""
    atts = attachments or []

    needed_cids = _extract_needed_cids(raw_html)
    if needed_cids:
        try:
            atts = deps.materialize_inline_attachments(
                provider=provider,
                account=account,
                folder=folder,
                uid=str(uid),
                attachments=atts,
                cache_key=int(cache_key),
                needed_cids=needed_cids,
            )
        except Exception:
            _logger.exception(
                "[Normalize] inline materialization failed (provider=%s uid=%s index_key=%s)",
                provider,
                uid,
                cache_key,
            )

    raw_base_url = (deps.base_url() or "").strip()
    base_url = raw_base_url or "http://invalid.local"
    if needed_cids and not raw_base_url:
        _logger.warning(
            "[Normalize] web.base.url missing/invalid; rewriting to fallback base URL (provider=%s uid=%s index_key=%s base_url=%s)",
            provider,
            uid,
            cache_key,
            base_url,
        )

    rewritten = deps.replace_cid_src(raw_html, atts, base_url=base_url)

    rewritten = deps.sanitize_email_html(rewritten)
    rewritten, did_scrub = _scrub_remaining_cid_references(rewritten)
    if did_scrub and needed_cids:
        _logger.info(
            "[Normalize] Unresolved cid: references scrubbed (provider=%s uid=%s index_key=%s)",
            provider,
            uid,
            cache_key,
        )

    if "cid:" in (rewritten or "").lower():
        _logger.info(
            "[Normalize] cid: still present after scrub; forcing final removal (provider=%s uid=%s index_key=%s)",
            provider,
            uid,
            cache_key,
        )
        rewritten = re.sub(r"(?i)url\(\s*cid:[^)]+\)", "", rewritten or "")
        rewritten = re.sub(r"cid:[^\s\"'>]+", "", rewritten or "", flags=re.IGNORECASE)

    if "about:blank" in (rewritten or "").lower():
        rewritten = rewritten.replace("about:blank", "")

    if base_url:
        rewritten = _absolutize_web_image_routes(rewritten, base_url)

    final_text = raw_text or deps.strip_html_to_text(rewritten) or ""
    return NormalizedBody(
        body_html=rewritten or "", body_text=final_text, attachments=atts
    )
