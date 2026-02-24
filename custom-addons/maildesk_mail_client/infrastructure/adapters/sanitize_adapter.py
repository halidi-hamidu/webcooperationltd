# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
SanitizeAdapter: Infrastructure adapter for SanitizeMessageBody use case.
Provides account settings access and tracking blocker integration.
"""

import logging

from ...domain.services.url_blocker import block_tracking_content

_logger = logging.getLogger(__name__)


class SanitizeAdapter:
    """
    Adapter for SanitizeMessageBody use case.
    Implements dependency protocols for message sanitization.
    """

    def __init__(self, env):
        self.env = env

    def get_account_block_tracking_setting(self, account_id: int) -> bool:
        """
        Check if account has tracking URL/pixel blocking enabled.

        Args:
            account_id: Odoo account ID

        Returns:
            True if blocking is enabled, False otherwise
        """
        try:
            account = self.env["mailbox.account"].browse(account_id)
            return bool(account.block_tracking_urls)
        except Exception as e:
            _logger.warning(f"Failed to get block_tracking_urls setting: {e}")
            return False

    def block_tracking_content(self, html: str) -> tuple:
        """
        Apply tracking blocking to HTML content.

        Args:
            html: Original HTML

        Returns:
            Tuple of (cleaned_html, pixels_blocked, urls_cleaned)
        """
        try:
            return block_tracking_content(html)
        except Exception as e:
            _logger.error(f"Tracking blocker failed: {e}")
            # Return original on failure
            return html, 0, 0
