# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Model tests for `models/mailbox_sync.py`.

Focus: RPC wiring to use cases (OpenMessage, OpenThreadMessages) without provider calls.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestMailboxSyncRPC(TransactionCase):
    """Integration-style tests for mailbox.sync RPC entrypoints."""

    def test_get_message_with_attachments_delegates_to_open_message(self):
        """RPC delegates to OpenMessage and forwards parameters deterministically."""

        captured = {}

        class DummyOpenMessage:
            def __init__(self, _deps):
                return None

            def execute(self, params):
                captured["index_id"] = params.index_id
                captured["uid"] = params.uid
                captured["folder_id"] = params.folder_id
                captured["account_id"] = params.account_id
                return {"ok": True, "id": params.index_id, "uid": params.uid}

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_sync.OpenMessage",
            DummyOpenMessage,
        ):
            res = self.env["mailbox.sync"].get_message_with_attachments(
                {
                    "index_id": 10,
                    "uid": "123",
                    "folder_id": 1,
                    "account_id": 2,
                    "is_internal_draft": False,
                }
            )

        self.assertTrue(res["ok"])
        self.assertEqual(
            captured, {"index_id": 10, "uid": "123", "folder_id": 1, "account_id": 2}
        )
