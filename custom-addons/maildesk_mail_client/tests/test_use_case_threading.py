# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for thread-related use cases.

Covers:
- `application/use_cases/open_thread_messages.py`
- `application/use_cases/fetch_thread.py`
Layer: tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from odoo.tests.common import TransactionCase

from ..application.use_cases.fetch_thread import FetchThread, FetchThreadParams
from ..application.use_cases.open_thread_messages import (
    OpenThreadMessages,
    OpenThreadMessagesParams,
)


@dataclass
class _DummyAccount:
    id: int


@dataclass
class _Idx:
    id: int
    uid: str
    folder: str
    sort_ts: int


class TestOpenThreadMessages(TransactionCase):
    """Unit tests for thread open (cache-only reads + sorting)."""

    def test_reads_cache_only_and_sorts_by_sort_ts(self):
        """Missing cache bodies are not hydrated; DTOs still sort by sort_ts."""

        account = _DummyAccount(id=1)
        idx_old = _Idx(id=10, uid="u1", folder="INBOX", sort_ts=1)
        idx_new = _Idx(id=11, uid="u2", folder="INBOX", sort_ts=2)

        cache_map = {
            10: {"body_html": "<p>old</p>", "body_text": "", "attachments": []}
        }

        class Deps:
            def account_browse(self, account_id: int):
                return account if int(account_id) == 1 else None

            def check_account_access(self, _account):
                return None

            def get_thread_index_records(self, _account, _thread_id: str):
                return [idx_new, idx_old]

            def folders_by_name(self, _account_id: int, folder_names):
                return {
                    name: {"id": 1, "folder_type": "inbox"} for name in folder_names
                }

            def cache_fetch_body_map(self, index_ids):
                return {i: cache_map[i] for i in index_ids if i in cache_map}

            def cache_resolve_canonical_index_id(self, index_id: int) -> int:
                return int(index_id)

            def build_open_message_dto_from_cache(
                self, *, index_rec, cached, account, folder
            ):
                return {
                    "id": index_rec.id,
                    "sort_ts": index_rec.sort_ts,
                    "body_html": cached["body_html"],
                }

            def hydrate_message(self, index_rec, folder):
                return {
                    "id": index_rec.id,
                    "sort_ts": index_rec.sort_ts,
                    "body_html": "",
                }

        out = OpenThreadMessages(Deps()).execute(
            OpenThreadMessagesParams(account_id=1, thread_id="t1", include_bodies=True)
        )

        self.assertEqual([m["id"] for m in out], [10, 11])
        self.assertEqual(out[0]["body_html"], "<p>old</p>")
        self.assertEqual(out[1]["body_html"], "")


class TestFetchThread(TransactionCase):
    """Unit tests for FetchThread → ThreadingService delegation."""

    def test_fetch_thread_with_thread_id_hydrates_via_get_message_with_attachments(
        self,
    ):
        """When a thread_id is provided, the thread is built from SSOT summaries and hydrated."""

        account = _DummyAccount(id=1)
        hydrated = {
            "id": 10,
            "uid": "u1",
            "folder_id": 1,
            "account_id": 1,
            "subject": "Hello",
        }

        class Deps:
            def is_gmail_account(self, _account):
                return False

            def gmail_build_service(self, _account):
                raise AssertionError("not gmail path")

            def gmail_get_thread_full(self, *_a, **_k):
                raise AssertionError("not gmail path")

            def get_thread_messages_from_db(
                self, _account, _thread_id: str, include_bodies: bool
            ):
                self.args = (_thread_id, include_bodies)
                return [{"id": 10, "uid": "u1", "folder_id": 1}]

            def get_message_with_attachments(self, params: dict):
                return hydrated if int(params.get("id")) == 10 else None

            def find_message_by_message_id(self, *_a, **_k):
                return None

        out = FetchThread(Deps()).execute(
            FetchThreadParams(
                account=account,
                message_id="<m@example.com>",
                thread_id="thread-1",
                include_bodies=True,
            )
        )
        self.assertEqual(out, [hydrated])
