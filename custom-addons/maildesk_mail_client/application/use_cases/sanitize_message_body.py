# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
SanitizeMessageBody Use-Case: Apply tracking URL/pixel blocking.
Returns cleaned HTML based on account settings.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SanitizeMessageBodyParams:
    """Parameters for message body sanitization."""

    body_html: str
    account_id: int


class SanitizeMessageBodyDeps(Protocol):
    """Dependencies for SanitizeMessageBody use case."""

    def get_account_block_tracking_setting(self, account_id: int) -> bool:
        """Check if account has tracking blocking enabled."""
        ...

    def block_tracking_content(self, html: str) -> tuple:
        """Apply tracking blocking. Returns (cleaned_html, pixels_blocked, urls_cleaned)."""
        ...


class SanitizeMessageBody:
    """
    Use-case: Sanitize message body by blocking tracking URLs and pixels.

    Responsibilities:
    - Check account settings
    - Apply tracking blocker if enabled
    - Return cleaned HTML
    """

    def __init__(self, deps: SanitizeMessageBodyDeps):
        self._deps = deps

    def execute(self, params: SanitizeMessageBodyParams) -> str:
        """
        Execute body sanitization.

        Args:
            params: SanitizeMessageBodyParams

        Returns:
            Cleaned HTML string (or original if blocking disabled)
        """
        # Check if tracking blocking is enabled for this account
        should_block = self._deps.get_account_block_tracking_setting(params.account_id)

        if not should_block:
            return params.body_html

        if not params.body_html:
            return params.body_html

        # Apply tracking blocker
        cleaned_html, pixels_blocked, urls_cleaned = self._deps.block_tracking_content(
            params.body_html
        )

        return cleaned_html
