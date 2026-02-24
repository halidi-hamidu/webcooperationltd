# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Outlook provider token utilities.

Centralizes token-related computations for MailDesk's Microsoft Graph integration.
Layer: infrastructure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

TOKEN_EXPIRY_SAFETY_SECONDS = 60


def compute_access_token_expiration_timestamp(
    *,
    expires_in_seconds: int,
    safety_seconds: int = TOKEN_EXPIRY_SAFETY_SECONDS,
) -> int:
    """
    Compute a Unix expiration timestamp (seconds) for an OAuth access token.

    Microsoft returns `expires_in` as a relative duration in seconds. Odoo's
    Outlook integration patterns store expiration as an *absolute* Unix
    timestamp (seconds since epoch). This helper converts the duration to an
    absolute timestamp using UTC and applies a safety buffer.

    Args:
        expires_in_seconds (int): Token TTL returned by Microsoft (`expires_in`).
        safety_seconds (int): Safety buffer subtracted from TTL to avoid edge
            cases where a token expires during a request.

    Returns:
        int: Unix timestamp in seconds (UTC).
    """
    ttl_seconds = int(expires_in_seconds or 0)
    buffer_seconds = max(int(safety_seconds or 0), 0)
    effective_ttl = max(ttl_seconds - buffer_seconds, 0)
    now = datetime.now(timezone.utc)
    return int((now + timedelta(seconds=effective_ttl)).timestamp())
