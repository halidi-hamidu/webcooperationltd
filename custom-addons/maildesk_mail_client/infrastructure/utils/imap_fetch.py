# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP fetch response utilities.

IMAP `FETCH` replies are represented as a mapping where keys are typically `bytes`
like `b"BODY[]"` or `b"BODY[TEXT]<0.2048>"`. When using partial fetches, the
server appends a `<start.count>` suffix to the returned key. This module offers
small helpers to extract body bytes in a stable, prioritized way.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable


def pick_imap_body_bytes(
    fetch_row: Mapping[Any, Any],
    *,
    priority_targets: Iterable[bytes] = (b"BODY[]", b"BODY[1]", b"BODY[TEXT]"),
) -> bytes:
    """
    Return the best available body bytes from a single IMAP FETCH row.

    The match is performed using substring containment (`target in key`) to
    support key variants like `b"BODY[]<0.16384>"` or `b"BODY[TEXT]<0.2048>"`.

    Args:
        fetch_row: One message row from an IMAP client's `fetch()` result.
        priority_targets: Byte substrings ordered by preference.

    Returns:
        Bytes suitable for preview extraction, or `b""` if no body-like field is found.
    """
    if not fetch_row:
        return b""

    body_bytes = b""
    found_priority = float("inf")

    for key, value in fetch_row.items():
        if isinstance(key, (bytes, bytearray)):
            key_bytes = bytes(key)
        elif isinstance(key, str):
            key_bytes = key.encode("utf-8", "ignore")
        else:
            continue

        for i, target in enumerate(priority_targets):
            if i >= found_priority:
                continue
            if target in key_bytes:
                body_bytes = value or b""
                found_priority = i
                if i == 0:
                    return body_bytes
                break

    return body_bytes
