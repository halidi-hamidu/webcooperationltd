# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Infrastructure: Email Preview Extraction

Extracts plain text preview from IMAP message bodies.
"""

from __future__ import annotations

import logging
import quopri
import re
from email import policy
from email.message import Message
from email.parser import BytesParser
from typing import Optional, Union

from bs4 import BeautifulSoup

from .html_sanitizer import strip_html_to_text as strip_html_to_text_strict
from .utils.preview_text import clean_preview_text, looks_like_base64
from .utils.rfc822 import (
    looks_like_header_block,
    looks_like_rfc822,
    split_rfc822_headers_and_body,
)

_logger = logging.getLogger(__name__)

MAX_PREVIEW_BYTES = 16_384
MAX_PREVIEW_CHARS = 200


def extract_imap_preview(
    blob: Optional[Union[bytes, str]],
    subject: Optional[str],
    *,
    max_len: int = MAX_PREVIEW_CHARS,
    max_bytes: int = MAX_PREVIEW_BYTES,
) -> str:
    """
    Extract a stable plain-text preview from an IMAP message blob.

    Args:
        blob: Raw IMAP payload. Usually RFC822 bytes, but may be bytes or str.
        subject: Message subject (used as fallback when body cannot be parsed).
        max_len: Maximum preview length (characters).
        max_bytes: Maximum bytes to process from `blob` to keep extraction fast.

    Returns:
        str: Preview text suitable for list display.
    """
    subject_fallback = (subject or "").strip()
    if not blob:
        return subject_fallback[:max_len]

    blob_bytes = _to_bytes(blob, max_bytes=max_bytes)
    if not blob_bytes:
        return subject_fallback[:max_len]

    rfc822_parts = split_rfc822_headers_and_body(blob_bytes)
    if rfc822_parts:
        preview = _extract_preview_from_rfc822(blob_bytes)
        if not preview:
            _headers, body_bytes = rfc822_parts
            preview = _extract_preview_fallback(body_bytes)
    else:
        if looks_like_header_block(blob_bytes):
            return subject_fallback[:max_len]
        preview = _extract_preview_fallback(blob_bytes)
    if not preview:
        return subject_fallback[:max_len]

    preview = clean_preview_text(preview)
    if len(preview) > max_len:
        preview = preview[: max(0, max_len - 3)].rstrip() + "..."
    return preview


def _to_bytes(blob: Union[bytes, str], *, max_bytes: int) -> bytes:
    if isinstance(blob, bytes):
        data = blob
    else:
        data = str(blob).encode("utf-8", "ignore")
    return data[:max_bytes]


def _extract_preview_from_rfc822(blob_bytes: bytes) -> str:
    """
    Parse RFC822/MIME bytes and extract a text/plain (preferred) or text/html
    preview.

    This relies on the stdlib `email` parser and correctly handles
    Content-Transfer-Encoding (base64/quoted-printable) when headers are present.
    """
    if not looks_like_rfc822(blob_bytes):
        return ""
    msg = _parse_email(blob_bytes)
    if not msg:
        return ""

    plain = _extract_first_text_part(msg, prefer_plain=True)
    if plain:
        return plain
    html = _extract_first_text_part(msg, prefer_plain=False)
    return html or ""


def _parse_email(blob_bytes: bytes) -> Optional[Message]:
    try:
        return BytesParser(policy=policy.default).parsebytes(blob_bytes)
    except Exception:
        return None


def _extract_first_text_part(msg: Message, *, prefer_plain: bool) -> str:
    want = ("text/plain", "text/html") if prefer_plain else ("text/html", "text/plain")
    parts = [msg] if not msg.is_multipart() else list(msg.walk())

    for content_type in want:
        for part in parts:
            if part.is_multipart():
                continue
            if (part.get_content_type() or "").lower() != content_type:
                continue
            text = _decode_part_text(part)
            text = _maybe_decode_quoted_printable(text)
            if content_type == "text/html":
                text = strip_html_to_text_strict(text)
            if text and text.strip():
                return text
    return ""


def _decode_part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""

    charset = (part.get_content_charset() or "").strip() or "utf-8"
    try:
        return payload.decode(charset, "replace")
    except LookupError:
        return payload.decode("utf-8", "replace")


_QP_HEX_RE = re.compile(r"=[0-9A-Fa-f]{2}")


def _maybe_decode_quoted_printable(text: str) -> str:
    if not text:
        return ""
    if "=\n" not in text and "=\r\n" not in text and not _QP_HEX_RE.search(text):
        return text
    try:
        decoded = quopri.decodestring(text.encode("utf-8", "ignore"))
        return decoded.decode("utf-8", "replace")
    except Exception:
        return text


def _extract_preview_fallback(blob_bytes: bytes) -> str:
    """
    Fallback for non-RFC822 blobs.

    Some IMAP servers return partial fragments (e.g., BODY[TEXT]) without MIME
    headers. This path keeps extraction fast and best-effort: it attempts to
    decode quoted-printable, strip HTML (including <style>), and returns a
    stable snippet.
    """
    raw = _decode_best_effort(blob_bytes)
    raw = _maybe_decode_quoted_printable(raw)
    if looks_like_base64(raw):
        return ""

    lowered = raw.lower()
    if "<html" in lowered or "<body" in lowered or "<style" in lowered:
        return strip_html_to_text_strict(raw)

    if "<" in raw and ">" in raw:
        try:
            return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
        except Exception as e:
            _logger.debug("HTML fallback failed: %s", e)
            return raw

    return raw


def _decode_best_effort(blob_bytes: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return blob_bytes.decode(enc, "ignore")
        except Exception:
            continue
    return ""
