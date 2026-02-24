# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/ingest_queue.py`.

Focus: deterministic queueing and batch-processing behavior using faked adapters.
Layer: tests.
"""

from __future__ import annotations

from datetime import datetime, timezone

from odoo.tests.common import TransactionCase

from ..application.use_cases.ingest_queue import (
    EnqueueIngestForMessageIndex,
    EnqueueIngestForMessageIndexParams,
    ProcessIngestQueueBatch,
    ProcessIngestQueueBatchParams,
    QueueContext,
)


class TestIngestQueueUseCases(TransactionCase):
    """Unit tests for ingest queue orchestration."""

    def test_enqueue_creates_queue_when_eligible(self):
        """Eligible index creates a queue entry exactly once."""

        class Deps:
            def index_exists(self, _index_id: int) -> bool:
                return True

            def should_ingest(self, _index_id: int) -> bool:
                return True

            def queue_find_by_index(self, _index_id: int):
                return None

            def queue_create(self, index_id: int, priority: int):
                self.args = (index_id, priority)
                return 5

        res = EnqueueIngestForMessageIndex(Deps()).execute(
            EnqueueIngestForMessageIndexParams(index_id=10, priority=7)
        )
        self.assertTrue(res["queued"])
        self.assertEqual(res["queue_id"], 5)

    def test_process_batch_marks_done_on_success(self):
        """ProcessIngestQueueBatch marks a queue item done after processing raw body."""

        calls = []
        now = datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)

        ctx = QueueContext(
            queue_id=1,
            state="pending",
            retry_count=0,
            processed_res_id=None,
            index_id=10,
            account_id=1,
            provider="imap",
            folder="INBOX",
            uid="1",
            message_id="<m@example.com>",
        )

        class Deps:
            def lock_acquire(self) -> bool:
                return True

            def lock_release(self) -> None:
                calls.append("lock_release")

            def now(self):
                return now

            def fetch_pending_queue_ids(self, batch: int, max_attempts: int, now_dt):
                return [1]

            def mark_queue_in_progress(self, queue_id: int, now_dt) -> bool:
                return True

            def get_queue_context(self, queue_id: int):
                return ctx if queue_id == 1 else None

            def find_mail_message_by_message_id(self, _message_id: str):
                return None

            def fetch_raw_body(self, _ctx: QueueContext):
                return b"raw"

            def queue_store_raw_body(self, queue_id: int, raw_body: bytes) -> None:
                calls.append(("store", queue_id, raw_body))

            def queue_mark_done(
                self, queue_id: int, processed_model=None, processed_res_id=None
            ) -> None:
                calls.append(("done", queue_id, processed_model, processed_res_id))

            def queue_mark_skipped(self, *_a, **_k):
                raise AssertionError("not expected")

            def queue_mark_failed(self, *_a, **_k):
                raise AssertionError("not expected")

            def mark_index_deleted(self, *_a, **_k):
                raise AssertionError("not expected")

            def message_process(self, account_id: int, raw_body: bytes):
                return {"model": "mail.message", "res_id": 42}

        done = ProcessIngestQueueBatch(Deps()).execute(
            ProcessIngestQueueBatchParams(batch=1)
        )

        self.assertEqual(done, 1)
        self.assertIn(("store", 1, b"raw"), calls)
        self.assertIn(("done", 1, "mail.message", 42), calls)
        self.assertIn("lock_release", calls)
