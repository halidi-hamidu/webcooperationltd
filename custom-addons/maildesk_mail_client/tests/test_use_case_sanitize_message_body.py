# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/sanitize_message_body.py`.

Focus: tracking-blocking toggle behavior via account settings.
Layer: tests.
"""

from __future__ import annotations

from odoo.tests.common import TransactionCase

from ..application.use_cases.sanitize_message_body import (
    SanitizeMessageBody,
    SanitizeMessageBodyParams,
)


class TestSanitizeMessageBody(TransactionCase):
    """Unit tests for message body sanitization."""

    def test_returns_original_when_blocking_disabled(self):
        """When blocking is disabled, the original HTML is returned unchanged."""

        calls = []

        class Deps:
            def get_account_block_tracking_setting(self, _account_id: int) -> bool:
                return False

            def block_tracking_content(self, html: str):
                calls.append(html)
                return html, 0, 0

        html = "<p>Hello</p>"
        out = SanitizeMessageBody(Deps()).execute(
            SanitizeMessageBodyParams(body_html=html, account_id=1)
        )
        self.assertEqual(out, html)
        self.assertEqual(calls, [])

    def test_applies_blocker_when_enabled(self):
        """When blocking is enabled, the blocker result is returned."""

        class Deps:
            def get_account_block_tracking_setting(self, _account_id: int) -> bool:
                return True

            def block_tracking_content(self, html: str):
                return "<p>clean</p>", 1, 2

        out = SanitizeMessageBody(Deps()).execute(
            SanitizeMessageBodyParams(body_html="<p>dirty</p>", account_id=1)
        )
        self.assertEqual(out, "<p>clean</p>")
