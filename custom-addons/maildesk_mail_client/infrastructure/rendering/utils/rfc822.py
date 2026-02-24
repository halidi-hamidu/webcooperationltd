# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
RFC822 helpers for message slices.

These utilities are used when the IMAP client fetches message bodies as RFC822
bytes (full messages or partial slices). The functions here are intentionally
generic and reusable across rendering/preview components.
"""

from __future__ import annotations

import re
from typing import Optional

_RFC822_HEADER_RE = re.compile(rb"(?m)^[A-Za-z0-9-]{1,64}:")
_RFC822_HEADER_LINE_RE = re.compile(rb"^[A-Za-z0-9-]{1,64}:")

_HEADER_BLOCK_SCAN_BYTES = 2048
_HEADER_BLOCK_MAX_LINES = 40
_HEADER_BLOCK_MIN_LINES = 5


def looks_like_rfc822(blob_bytes: bytes) -> bool:
    """
    Best-effort detection of an RFC822 message slice.

    Returns True when a header/body separator is present and the header section
    contains at least one RFC822-like header line.
    """
    if not blob_bytes:
        return False

    sep = blob_bytes.find(b"\r\n\r\n")
    if sep == -1:
        sep = blob_bytes.find(b"\n\n")
    if sep == -1:
        return False

    return bool(_RFC822_HEADER_RE.search(blob_bytes[:sep]))


def split_rfc822_headers_and_body(blob_bytes: bytes) -> Optional[tuple[bytes, bytes]]:
    """
    Split an RFC822 slice into `(headers, body)`.

    Returns None when no header/body separator is present or headers do not look
    like RFC822 headers.
    """
    if not blob_bytes:
        return None

    sep = blob_bytes.find(b"\r\n\r\n")
    sep_len = 4
    if sep == -1:
        sep = blob_bytes.find(b"\n\n")
        sep_len = 2
    if sep == -1:
        return None

    headers = blob_bytes[:sep]
    if not _RFC822_HEADER_RE.search(headers):
        return None

    body = blob_bytes[sep + sep_len :]
    return headers, body


def looks_like_header_block(blob_bytes: bytes) -> bool:
    """
    Detect a truncated RFC822 header-only slice (no body separator).

    This is used for preview extraction to avoid showing a wall of headers when
    the IMAP slice contains only headers.
    """
    if not blob_bytes:
        return False

    chunk = blob_bytes[:_HEADER_BLOCK_SCAN_BYTES]
    if b"\r\n\r\n" in chunk or b"\n\n" in chunk:
        return False

    header_lines = 0
    for ln in chunk.splitlines()[:_HEADER_BLOCK_MAX_LINES]:
        if _RFC822_HEADER_LINE_RE.match(ln):
            header_lines += 1
    return header_lines >= _HEADER_BLOCK_MIN_LINES
