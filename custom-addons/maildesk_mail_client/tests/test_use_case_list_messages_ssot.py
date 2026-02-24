# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/list_messages_ssot.py`.

Focus: SSOT miss signaling and folder-scoped listing behavior.
Layer: tests.
"""

from __future__ import annotations

from datetime import datetime

from odoo.tests.common import TransactionCase

from ..application.use_cases.list_messages_ssot import (
    ListMessagesParams,
    ListMessagesSsot,
)


class TestListMessagesSsot(TransactionCase):
    """Unit tests for SSOT listing logic."""

    def test_returns_empty_when_registry_not_ready(self):
        """When the registry isn't ready, listing returns an empty result without ssot_miss."""

        class Deps:
            def registry_ready(self) -> bool:
                return False

        res = ListMessagesSsot(Deps()).execute(ListMessagesParams())
        self.assertEqual(res["records"], [])
        self.assertEqual(res["totalMessagesCount"], 0)
        self.assertFalse(res["ssot_miss"])

    def test_folder_listing_sets_ssot_miss_when_folder_has_no_indexed_rows(self):
        """Empty folder with no indexed rows returns ssot_miss=True to trigger bootstrap."""

        class Folder:
            id = 1

        class Account:
            id = 1

        class Deps:
            def registry_ready(self) -> bool:
                return True

            def folder_browse(self, _folder_id: int):
                return Folder()

            def folder_exists(self, _folder) -> bool:
                return True

            def folder_account(self, _folder):
                return Account()

            def folder_imap_name(self, _folder):
                return "INBOX"

            def folder_display_name(self, _folder):
                return "Inbox"

            def folder_type(self, _folder):
                return "inbox"

            def accounts_for_id(self, _account_id: int):
                return []

            def user_accounts(self):
                return []

            def is_gmail_account(self, _account):
                return False

            def is_outlook_account(self, _account):
                return False

            def search_index_records(self, _account, _folder_name, _provider, _params):
                return [], 0

            def has_any_indexed(self, _account, _folder_name, _provider=None):
                return False

            def build_records_from_index(
                self, _account, _folder, _index_records, _partner_cache
            ):
                return []

            def apply_state_overlays(self, *_a, **_k):
                raise AssertionError("not used on SSOT path")

            def apply_overrides_and_tags(self, *_a, **_k):
                raise AssertionError("not used on SSOT path")

            def get_tags_for_message_ids(self, *_a, **_k):
                raise AssertionError("not used on SSOT path")

            def append_local_drafts(self, *, account, folder, records, total, search):
                return records, total

            def safe_dt(self, rec):
                return datetime(1970, 1, 1)

            def resolve_inbox_folder(self, _account):
                return None

        res = ListMessagesSsot(Deps()).execute(ListMessagesParams(folder_id=1))
        self.assertEqual(res["records"], [])
        self.assertTrue(res["ssot_miss"])
