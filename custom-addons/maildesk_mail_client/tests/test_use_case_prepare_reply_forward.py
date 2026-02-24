# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for composer preparation use cases.

Covers:
- `application/use_cases/prepare_reply.py`
- `application/use_cases/prepare_forward.py`
Layer: tests.
"""

from __future__ import annotations

from odoo.tests.common import TransactionCase

from ..application.use_cases.prepare_forward import PrepareForward, PrepareForwardParams
from ..application.use_cases.prepare_reply import PrepareReply, PrepareReplyParams


class TestPrepareReplyForward(TransactionCase):
    """Unit tests for composer preparation (no provider/network)."""

    def test_prepare_reply_all_filters_own_email_and_builds_subject(self):
        """Reply-all includes sender + other recipients, excluding the account's own email."""

        class Deps:
            def get_message(self, _msg_key):
                return {
                    "account_id": [1, "Acc"],
                    "subject": "Hello",
                    "email_from": "sender@example.com",
                    "to_addrs": "me@example.com, other@example.com",
                    "cc_addrs": "cc1@example.com, me@example.com",
                    "body_html": "<p>Body</p>",
                    "formatted_date": "2025-01-01",
                    "sender_display_name": "Sender",
                }

            def get_account_email(self, _account_id: int) -> str:
                return "me@example.com"

            def parse_email_list(self, email_str: str):
                return [e.strip() for e in (email_str or "").split(",") if e.strip()]

            def get_account_sender_name(self, _account_id: int) -> str:
                return "Sender Name"

        dto = PrepareReply(Deps()).execute(
            PrepareReplyParams(msg_key=123, reply_all=True)
        )

        self.assertEqual(dto["subject"], "Re: Hello")
        self.assertIn("sender@example.com", dto["to"])
        self.assertIn("other@example.com", dto["to"])
        self.assertNotIn("me@example.com", [x.lower() for x in dto["to"]])
        self.assertEqual(dto["cc"], ["cc1@example.com"])

    def test_prepare_forward_includes_attachments_and_prefixes_subject(self):
        """Forward includes original attachments and prefixes subject with Fwd:."""

        class Deps:
            def get_message(self, _msg_key):
                return {
                    "account_id": 1,
                    "subject": "Hello",
                    "email_from": "sender@example.com",
                    "to_addrs": "to@example.com",
                    "body_html": "<p>Body</p>",
                    "attachments": [{"id": 1, "name": "a.txt"}],
                    "formatted_date": "2025-01-01",
                }

            def get_account_sender_name(self, _account_id: int) -> str:
                return "Sender Name"

        dto = PrepareForward(Deps()).execute(PrepareForwardParams(msg_key=123))

        self.assertEqual(dto["subject"], "Fwd: Hello")
        self.assertEqual(
            dto["attachments"],
            [{"id": 1, "name": "a.txt", "mimetype": "", "access_token": ""}],
        )
