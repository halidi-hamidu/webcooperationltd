# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Ingest Queue.

Implements the application-level use case for Ingest Queue.
Layer: application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from dateutil.relativedelta import relativedelta

from ...domain.services.ingestion import compute_backoff_minutes


@dataclass(frozen=True)
class EnqueueIngestForMessageIndexParams:
    index_id: int
    priority: int = 10


@dataclass(frozen=True)
class ScanSSOTForIngestionParams:
    batch: int = 500


@dataclass(frozen=True)
class ProcessIngestQueueBatchParams:
    batch: int = 40
    max_attempts: int = 5


@dataclass(frozen=True)
class RecoverStuckIngestJobsParams:
    timeout_minutes: int = 30


@dataclass(frozen=True)
class QueueContext:
    queue_id: int
    state: str
    retry_count: int
    processed_res_id: Optional[int]
    index_id: int
    account_id: int
    provider: str
    folder: str
    uid: str
    message_id: Optional[str]


@dataclass(frozen=True)
class MailMessageInfo:
    model: Optional[str]
    res_id: Optional[int]


@dataclass(frozen=True)
class StuckQueueInfo:
    queue_id: int
    retry_count: int


class EnqueueIngestForMessageIndexDeps(Protocol):
    def index_exists(self, index_id: int) -> bool: ...
    def should_ingest(self, index_id: int) -> bool: ...
    def queue_find_by_index(self, index_id: int) -> Optional[int]: ...
    def queue_create(self, index_id: int, priority: int) -> Optional[int]: ...


class ScanSSOTForIngestionDeps(Protocol):
    def lock_acquire(self) -> bool: ...
    def lock_release(self) -> None: ...
    def scan_candidate_index_ids(self, batch: int) -> List[int]: ...


class ProcessIngestQueueBatchDeps(Protocol):
    def lock_acquire(self) -> bool: ...
    def lock_release(self) -> None: ...
    def now(self): ...
    def fetch_pending_queue_ids(
        self, batch: int, max_attempts: int, now
    ) -> List[int]: ...
    def mark_queue_in_progress(self, queue_id: int, now) -> bool: ...
    def get_queue_context(self, queue_id: int) -> Optional[QueueContext]: ...
    def find_mail_message_by_message_id(
        self, message_id: str
    ) -> Optional[MailMessageInfo]: ...
    def fetch_raw_body(self, ctx: QueueContext) -> Optional[bytes]: ...
    def queue_store_raw_body(self, queue_id: int, raw_body: bytes) -> None: ...
    def queue_mark_done(
        self,
        queue_id: int,
        processed_model: Optional[str],
        processed_res_id: Optional[int],
    ) -> None: ...
    def queue_mark_skipped(
        self,
        queue_id: int,
        error_message: str,
        processed_model: Optional[str] = None,
        processed_res_id: Optional[int] = None,
    ) -> None: ...
    def queue_mark_failed(
        self,
        queue_id: int,
        retry_count: int,
        next_try_at,
        error_message: str,
    ) -> None: ...
    def mark_index_deleted(self, index_id: int) -> None: ...
    def message_process(self, account_id: int, raw_body: bytes): ...


class RecoverStuckIngestJobsDeps(Protocol):
    def now(self): ...
    def list_stuck_in_progress(self, cutoff) -> List[StuckQueueInfo]: ...
    def queue_mark_failed(
        self,
        queue_id: int,
        retry_count: int,
        next_try_at,
        error_message: str,
    ) -> None: ...


class EnqueueIngestForMessageIndex:
    def __init__(self, deps: EnqueueIngestForMessageIndexDeps):
        self._deps = deps

    def execute(self, params: EnqueueIngestForMessageIndexParams) -> dict:
        if not self._deps.index_exists(params.index_id):
            return {"queued": False, "reason": "missing_index"}

        if not self._deps.should_ingest(params.index_id):
            return {"queued": False, "reason": "not_eligible"}

        existing = self._deps.queue_find_by_index(params.index_id)
        if existing:
            return {"queued": False, "reason": "already_queued", "queue_id": existing}

        queue_id = self._deps.queue_create(params.index_id, params.priority)
        return {"queued": bool(queue_id), "queue_id": queue_id}


class ScanSSOTForIngestion:
    def __init__(self, deps: ScanSSOTForIngestionDeps, enqueue_use_case):
        self._deps = deps
        self._enqueue = enqueue_use_case

    def execute(self, params: ScanSSOTForIngestionParams) -> int:
        if not self._deps.lock_acquire():
            return 0

        try:
            index_ids = self._deps.scan_candidate_index_ids(params.batch)
            if not index_ids:
                return 0

            enqueued = 0
            for index_id in index_ids:
                res = self._enqueue.execute(
                    EnqueueIngestForMessageIndexParams(index_id=index_id)
                )
                if res.get("queued"):
                    enqueued += 1
            return enqueued
        finally:
            self._deps.lock_release()


class ProcessIngestQueueBatch:
    def __init__(self, deps: ProcessIngestQueueBatchDeps):
        self._deps = deps

    def execute(self, params: ProcessIngestQueueBatchParams) -> int:
        if not self._deps.lock_acquire():
            return 0

        try:
            now = self._deps.now()
            queue_ids = self._deps.fetch_pending_queue_ids(
                params.batch, params.max_attempts, now
            )
            if not queue_ids:
                return 0

            done = 0
            for queue_id in queue_ids:
                ctx = self._deps.get_queue_context(queue_id)
                if not ctx:
                    continue

                if ctx.state == "done" and ctx.processed_res_id:
                    self._deps.queue_mark_skipped(queue_id, "Already processed")
                    continue

                if not self._deps.mark_queue_in_progress(queue_id, now):
                    continue

                ctx = self._deps.get_queue_context(queue_id)
                if not ctx:
                    self._deps.queue_mark_failed(
                        queue_id,
                        retry_count=1,
                        next_try_at=now,
                        error_message="No linked index record",
                    )
                    continue

                if not ctx.index_id or not ctx.account_id:
                    self._deps.queue_mark_failed(
                        queue_id,
                        retry_count=ctx.retry_count + 1,
                        next_try_at=now,
                        error_message="No linked account or index",
                    )
                    continue

                if ctx.message_id:
                    existing = self._deps.find_mail_message_by_message_id(
                        ctx.message_id
                    )
                    if existing:
                        self._deps.queue_mark_skipped(
                            queue_id,
                            f"Already in mail.message (id={existing.res_id})",
                            processed_model=existing.model,
                            processed_res_id=existing.res_id,
                        )
                        continue

                try:
                    raw_body = self._deps.fetch_raw_body(ctx)
                except Exception as e:
                    self._handle_failure(queue_id, ctx.retry_count, now, e)
                    continue

                if not raw_body:
                    self._deps.mark_index_deleted(ctx.index_id)
                    self._deps.queue_mark_skipped(
                        queue_id,
                        "Message not found on provider - marked deleted",
                    )
                    continue

                self._deps.queue_store_raw_body(queue_id, raw_body)

                try:
                    result = self._deps.message_process(ctx.account_id, raw_body)
                except ValueError as e:
                    if "No possible route found" in str(e):
                        self._deps.queue_mark_skipped(queue_id, str(e))
                        continue
                    self._handle_failure(queue_id, ctx.retry_count, now, e)
                    continue
                except Exception as e:
                    self._handle_failure(queue_id, ctx.retry_count, now, e)
                    continue

                processed_model, processed_res_id = self._parse_process_result(result)

                # SSOT is already complete from backfill (has real subject/from/etc)
                # Ingest only handles body/attachments

                self._deps.queue_mark_done(
                    queue_id,
                    processed_model=processed_model,
                    processed_res_id=processed_res_id,
                )
                done += 1

            return done
        finally:
            self._deps.lock_release()

    def _handle_failure(
        self, queue_id: int, retry_count: int, now, exc: Exception
    ) -> None:
        backoff_minutes = compute_backoff_minutes(retry_count)
        next_try = now + relativedelta(minutes=backoff_minutes)
        self._deps.queue_mark_failed(
            queue_id,
            retry_count=retry_count + 1,
            next_try_at=next_try,
            error_message=str(exc)[:1000],
        )

    def _parse_process_result(self, result):
        processed_model = None
        processed_res_id = None

        if isinstance(result, dict):
            processed_model = result.get("model")
            processed_res_id = result.get("res_id")
        elif result:
            try:
                if hasattr(result, "model") and hasattr(result, "res_id"):
                    processed_model = result.model
                    processed_res_id = result.res_id
            except Exception:
                pass

        return processed_model, processed_res_id


class RecoverStuckIngestJobs:
    def __init__(self, deps: RecoverStuckIngestJobsDeps):
        self._deps = deps

    def execute(self, params: RecoverStuckIngestJobsParams) -> int:
        now = self._deps.now()
        cutoff = now - relativedelta(minutes=params.timeout_minutes)
        stuck = self._deps.list_stuck_in_progress(cutoff)
        if not stuck:
            return 0

        recovered = 0
        for item in stuck:
            backoff_minutes = compute_backoff_minutes(item.retry_count)
            next_try = now + relativedelta(minutes=backoff_minutes)
            self._deps.queue_mark_failed(
                item.queue_id,
                retry_count=item.retry_count + 1,
                next_try_at=next_try,
                error_message="Recovered from stuck in_progress",
            )
            recovered += 1

        return recovered
