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

from ..application.use_cases.ui_actions import SetFlags, SetFlagsParams
from .common import FakeNotifier


class TestUIActions(TransactionCase):
    """Unit tests for UI action use cases."""

    def test_set_flags_emits_flags_changed_and_unread_count_changed(self):
        """SetFlags updates index and emits notifier events grouped by folder."""

        updated = []

        class Deps:
            env = None

            def index_update_direct(
                self, index_id: int, is_read=None, is_starred=None
            ) -> bool:
                updated.append((index_id, is_read, is_starred))
                return True

            def get_msg_ssot_info(self, index_id: int):
                return {"account_id": 1, "folder": "INBOX", "uid": str(index_id)}

            def update_folder_unread_count(self, account_id: int, folder: str) -> int:
                return 5

        notifier = FakeNotifier()
        res = SetFlags(Deps(), notifier=notifier).execute(
            SetFlagsParams(message_ids=["10", "11"], is_read=True)
        )

        self.assertTrue(res)
        self.assertEqual(updated, [(10, True, None), (11, True, None)])

        calls = notifier.calls
        self.assertIn("notify_flags_changed", [c.name for c in calls])
        self.assertIn("notify_unread_count_changed", [c.name for c in calls])
