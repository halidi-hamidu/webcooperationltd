# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for partner-related use cases.

Covers:
- `application/use_cases/create_partner_from_message.py`
- `application/use_cases/trust_partner.py`
Layer: tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from odoo.tests.common import TransactionCase

from ..application.use_cases.create_partner_from_message import (
    CreatePartnerFromMessage,
    CreatePartnerFromMessageParams,
)
from ..application.use_cases.trust_partner import TrustPartner, TrustPartnerParams


@dataclass
class _DummyUser:
    id: int


@dataclass
class _DummyPartner:
    id: int
    trusted_by_user_id: _DummyUser | None = None


class TestPartnerActions(TransactionCase):
    """Unit tests for partner creation and trust flows."""

    def test_create_partner_from_message_creates_when_missing(self):
        """When no partner exists for email, the use case creates and returns an action."""

        created = []

        class Deps:
            def partner_search(self, _domain: list):
                return False

            def partner_create(self, vals: dict):
                created.append(vals)
                return _DummyPartner(id=10)

            def partner_id(self, partner):
                return partner.id

            def env_translate(self, text: str) -> str:
                return text

            def defaults_from_email(self, email: str, display_name: str) -> dict:
                return {
                    "name": display_name or email,
                    "lang": "en_US",
                    "tz": "UTC",
                    "website": "",
                }

            def get_valid_lang(self, lang: str) -> str:
                return lang

        action = CreatePartnerFromMessage(Deps()).execute(
            CreatePartnerFromMessageParams(
                email_from="Sender <sender@example.com>",
                sender_display_name="Sender",
            )
        )

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["res_id"], 10)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["email"], "sender@example.com")

    def test_trust_partner_marks_existing_partner_trusted(self):
        """TrustPartner writes trusted flags and returns partner metadata for UI."""

        partner = _DummyPartner(id=10, trusted_by_user_id=_DummyUser(id=7))
        writes = []

        class Deps:
            def partner_search(self, _domain: list):
                return partner

            def partner_browse(self, _partner_id: int):
                return partner

            def partner_exists(self, _partner) -> bool:
                return True

            def partner_create(self, _vals: dict):
                raise AssertionError("must not create when partner exists")

            def partner_write(self, _partner, vals: dict) -> None:
                writes.append(vals)

            def partner_id(self, p) -> int:
                return p.id

            def partner_trusted_by_user_id(self, p):
                return p.trusted_by_user_id

            def env_user_id(self) -> int:
                return 7

            def env_translate(self, text: str) -> str:
                return text

            def extract_email_address(self, email_from: str) -> str:
                return "sender@example.com"

        res = TrustPartner(Deps()).execute(
            TrustPartnerParams(
                message={
                    "email_from": "sender@example.com",
                    "sender_display_name": "Sender",
                }
            )
        )

        self.assertEqual(res["partner_id"], 10)
        self.assertTrue(res["trusted_partner"])
        self.assertEqual(res["trusted_by_user_id"], 7)
        self.assertEqual(len(writes), 1)
        self.assertTrue(writes[0]["trusted_partner"])
