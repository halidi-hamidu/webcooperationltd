# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/ui_actions.py`.

Focus: SSOT flag updates emit correct notifier events deterministically.
Layer: tests.
"""

from __future__ import annotations

from odoo.tests.common import TransactionCase
from ..application.use_cases.ui_actions import UpdateTags, UpdateTagsParams
from .common import FakeNotifier


class TestUIActionsTags(TransactionCase):
    """Unit tests for UI action UpdateTags."""

    def test_update_tags_verifies_success_and_emits_events(self):
        """UpdateTags verifies backend success before emitting events."""

        updated_calls = []

        class Deps:
            env = None

            def index_update_tags(
                self, account_id: int, folder: str, uid: str, tag_ids: list
            ) -> dict | None:
                updated_calls.append((account_id, folder, uid, tag_ids))
                # Return truthy dict on success
                return {"index_id": int(uid), "tags": [{"id": t} for t in tag_ids]}

            def get_msg_ssot_info(self, index_id: int):
                return {"account_id": 1, "folder": "INBOX", "uid": str(index_id)}

        notifier = FakeNotifier()
        # Test success case
        res = UpdateTags(Deps(), notifier=notifier).execute(
            UpdateTagsParams(message_uids=["10"], tag_ids=[99])
        )

        self.assertTrue(res)
        self.assertEqual(updated_calls, [(1, "INBOX", "10", [99])])

        calls = notifier.calls
        self.assertIn("notify_tags_changed", [c.name for c in calls])
        # Verify notification payload
        notify_call = next(c for c in calls if c.name == "notify_tags_changed")
        self.assertEqual(notify_call.kwargs["tag_ids"], [99])

    def test_update_tags_handles_failure(self):
        """UpdateTags does NOT emit events if backend update fails."""

        class Deps:
            env = None

            def index_update_tags(
                self, account_id: int, folder: str, uid: str, tag_ids: list
            ) -> dict | None:
                # Return None (falsy) to simulate failure
                return None

            def get_msg_ssot_info(self, index_id: int):
                return {"account_id": 1, "folder": "INBOX", "uid": str(index_id)}

        notifier = FakeNotifier()
        res = UpdateTags(Deps(), notifier=notifier).execute(
            UpdateTagsParams(message_uids=["10"], tag_ids=[99])
        )

        self.assertFalse(res)  # Should return False on failure

        calls = notifier.calls
        self.assertEqual(len(calls), 0)  # No notifications emitted
