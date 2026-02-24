# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Sync IMAP Folder.

Implements the application-level use case for Sync IMAP Folder.
Layer: application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import psycopg2
from dateutil.relativedelta import relativedelta
from odoo import fields

from ..services.imap_client_service import build_authenticated_imap_client
from ...infrastructure.adapters.ingest_queue_adapter import IngestQueueAdapter
from ...domain.contracts import Message
from ...domain.services.normalization import msgid_header, norm_msgid, parse_msgid_list
from ...domain.value_objects import MailFlags
from ...infrastructure.providers.imap.utils import has_attachments_from_bodystructure
from ...infrastructure.utils.email_utils import (
    decode_header_value,
    parse_sender_header,
)
from ...infrastructure.rendering.preview_extractor import (
    MAX_PREVIEW_BYTES,
    extract_imap_preview,
)
from ...infrastructure.utils.imap_fetch import pick_imap_body_bytes
from .ingest_queue import (
    EnqueueIngestForMessageIndex,
    EnqueueIngestForMessageIndexParams,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImapFolderStatus:
    """IMAP folder status (uidvalidity, uidnext, modseq)."""

    uidvalidity: int
    uidnext: int
    highest_modseq: Optional[int]


class SyncImapFolderIncremental:
    """
    IMAP folder incremental sync (append-only + flag convergence + delete detection).

    Multi-folder support: Syncs ONE folder per execution using round-robin selection.
    Reconciliation detects server-side deletions via SSOT diff.
    """

    def __init__(
        self,
        env,
        *,
        notifier,  # SSotChangeNotifier Protocol (injected dependency)
        lease_ttl_seconds: int = 300,
        uid_batch_size: int = 50,
        max_uids_per_run: int = 500,
        flag_batch_size: int = 200,
    ):
        self.env = env
        self.notifier = notifier  # Store for use in _update_flags and _upsert_records
        self.lease_ttl_seconds = lease_ttl_seconds
        self.uid_batch_size = uid_batch_size
        self.max_uids_per_run = max_uids_per_run
        self.flag_batch_size = flag_batch_size

        # Must match `models/mailbox_folder.py` to enforce cross-entrypoint exclusion.
        self._folder_lock_namespace = 48232

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, account_id: int) -> dict:
        Account = self.env["mailbox.account"].sudo()
        account = Account.browse(int(account_id))
        if not account.exists() or account.is_gmail or account.is_outlook:
            return {"ok": False, "reason": "not_imap"}

        if account.backoff_until and account.backoff_until > fields.Datetime.now():
            return {"ok": False, "reason": "backoff"}

        Lease = self.env["maildesk.account_lease"].sudo()
        owner = f"imap-inbox:{self.env.cr.dbname}:{account.id}"
        if not Lease.try_acquire(
            account.id, ttl_seconds=self.lease_ttl_seconds, owner=owner
        ):
            return {"ok": False, "reason": "lease_locked"}

        try:
            return self._sync_account(account, owner)
        finally:
            Lease.release(account.id, owner=owner)

    # ------------------------------------------------------------------
    # Core flow
    # ------------------------------------------------------------------

    def _sync_account(self, account, owner: str) -> dict:
        # Select MULTIPLE folders for batch sync (cost-limited, not entity-limited)
        folders = self._select_folders_for_sync(account, limit=10)

        if not folders:
            return {"ok": False, "reason": "no_folders_to_sync"}

        _logger.info(
            f"[Multi-Folder Sync] Selected {len(folders)} folders for account={account.id}"
        )

        # Single IMAP connection for all selected folders
        client = self._open_client(account)
        try:
            return self._sync_multiple_folders(account, folders, client, owner)
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _sync_multiple_folders(self, account, folders, client, owner: str) -> dict:
        """
        Sync multiple folders in one IMAP session.
        Cost-limited by max_uids_per_run across all folders.
        Isolates failures: one bad folder does not block others.
        """
        total_uids_fetched = 0
        uid_budget_remaining = self.max_uids_per_run
        results = []

        for folder in folders:
            if uid_budget_remaining <= 0:
                _logger.info(
                    f"[Multi-Folder Sync] UID budget exhausted after {len(results)} folders, "
                    f"remaining {len(folders) - len(results)} folders deferred"
                )
                break

            # Wrap each folder in savepoint to prevent transaction abortion
            try:
                with self.env.cr.savepoint():
                    result = self._sync_one_folder(
                        account, folder, client, owner, uid_budget_remaining
                    )
                    fetched = result.get("fetched", 0)
                    total_uids_fetched += fetched
                    uid_budget_remaining -= fetched
                    ok = bool(result.get("ok"))
                    results.append(
                        {
                            "folder": folder.imap_name,
                            "ok": ok,
                            "fetched": fetched,
                            "reason": result.get("reason"),
                            "error": result.get("error"),
                        }
                    )
            except Exception as e:
                # Check for serialization failure (concurrent update/deadlock)
                # We must re-raise so Odoo/Postgres can retry the transaction safely.
                # Do NOT try to _record_error as that requires DB writes which will fail.
                if isinstance(e, psycopg2.errors.SerializationFailure):
                    raise e

                # For other errors, isolate failure: log error, record in folder, continue
                self._record_error(account, folder, e)
                results.append(
                    {
                        "folder": folder.imap_name,
                        "ok": False,
                        "error": str(e),
                    }
                )
                _logger.warning(
                    f"[Multi-Folder Sync] Folder {folder.imap_name} failed: {e}, continuing..."
                )

        succeeded = sum(1 for r in results if r.get("ok"))
        _logger.info(
            f"[Multi-Folder Sync] Completed: {succeeded}/{len(results)} folders synced, "
            f"total UIDs: {total_uids_fetched}"
        )

        return {
            "ok": True,
            "folders_attempted": len(results),
            "folders_synced": succeeded,
            "total_fetched": total_uids_fetched,
        }

    def _sync_one_folder(
        self, account, folder, client, owner: str, uid_budget: int
    ) -> dict:
        if folder.sync_state != "incremental":
            return {
                "ok": False,
                "reason": "backfill_not_complete",
                "sync_state": folder.sync_state,
                "message": f"Folder sync_state is '{folder.sync_state}', incremental sync requires 'incremental' state",
            }

        if not self._try_acquire_folder_sync_lock(folder.id):
            return {"ok": False, "reason": "folder_locked"}

        try:
            folder_name = folder.imap_name or folder.name
            status = self._get_folder_status(client, folder_name)

            uidvalidity_changed = (
                folder.uid_validity
                and status.uidvalidity
                and int(folder.uid_validity) != int(status.uidvalidity)
            )
            if uidvalidity_changed:
                folder.write({"sync_state": "backfill_pending", "last_uid": 0})
                self._reset_uidvalidity(
                    account, folder, folder_name, status.uidvalidity
                )
                return {
                    "ok": False,
                    "reason": "uidvalidity_changed",
                    "message": "UIDVALIDITY changed, folder reset to backfill_pending",
                }

            # Capture SSOT state before sync for reconciliation.
            ssot_before = self._capture_ssot_state(account, folder_name)

            last_uid = int(folder.last_uid or 0)
            if uidvalidity_changed:
                last_uid = 0

            # Forward Drift Detection: If local last_uid is >= server's NEXT UID,
            # we are in an impossible state (synced a future message).
            # This can happen if server state was reset without UIDVALIDITY change,
            # or if DB was restored/copied improperly.
            if status.uidnext and last_uid >= status.uidnext:
                _logger.warning(
                    "[IMAP Sync] Folder %s forward drift detected: last_uid=%s >= uidnext=%s. Forcing reset.",
                    folder_name,
                    last_uid,
                    status.uidnext,
                )
                folder.write({"sync_state": "backfill_pending", "last_uid": 0})
                return {
                    "ok": False,
                    "reason": "uid_drift",
                    "message": f"last_uid {last_uid} >= uidnext {status.uidnext}, forcing reset",
                }

            start_uid = last_uid + 1
            end_uid = max(int(status.uidnext) - 1, 0)

            processed_uids: List[int] = []
            if start_uid <= end_uid and uid_budget > 0:
                # Respect UID budget passed from multi-folder sync. This bound is
                # about "how wide of a UID range we will scan", not an IMAP UID
                # value ceiling for the server.
                capped_end = min(end_uid, start_uid + uid_budget - 1)

                # Do not assume UIDs are contiguous: SEARCH first and only fetch
                # existing UIDs. This prevents advancing last_uid past messages we
                # failed to fetch/parse and avoids "missing mails" symptoms.
                try:
                    server_uids = (
                        client.search(["UID", f"{start_uid}:{capped_end}"]) or []
                    )
                except Exception as e:
                    raise RuntimeError(
                        f"IMAP SEARCH failed for folder={folder_name} uid_range={start_uid}:{capped_end}: {e}"
                    ) from e

                server_uids = sorted({int(u) for u in server_uids if u})
                for chunk in self._chunks(server_uids, self.uid_batch_size):
                    records = self._fetch_message_batch(
                        client, folder_name, account, chunk
                    )
                    if records:
                        self._upsert_records(account, folder, records)
                        for m in records:
                            try:
                                processed_uids.append(int(m.id))
                            except Exception:
                                continue
                    self._renew_lease(account_id=account.id, owner=owner)

                if server_uids and not processed_uids:
                    raise RuntimeError(
                        f"IMAP fetch returned 0 parsed messages for folder={folder_name} "
                        f"uid_range={start_uid}:{capped_end} (uids={len(server_uids)})"
                    )

            new_last_uid = max(processed_uids) if processed_uids else last_uid
            new_modseq = self._sync_flags(client, account, folder, status, owner)

            # Capture provider state after sync and reconcile.
            provider_after = self._capture_provider_state(client)
            self._reconcile_and_emit(account, folder_name, ssot_before, provider_after)

            vals = {
                "uid_validity": int(status.uidvalidity or 0),
                "last_uid": int(new_last_uid or 0),
                "last_sync_at": fields.Datetime.now(),
                "last_error": False,
                # Phase 2 Completion: Clear dirty flag & update scan baselines
                "needs_sync": False,
                "last_uidnext": int(status.uidnext),
                "last_highest_modseq": str(new_modseq or status.highest_modseq or "0"),
            }
            if new_modseq is not None:
                vals["sync_modseq"] = str(new_modseq)

            folder.write(vals)
            account.write({"backoff_until": False})

            return {
                "ok": True,
                "fetched": len(processed_uids),
                "last_uid": new_last_uid,
            }
        except Exception as e:
            if isinstance(e, psycopg2.errors.SerializationFailure):
                raise e
            self._record_error(account, folder, e)
            return {"ok": False, "error": str(e)}

    def _try_acquire_folder_sync_lock(self, folder_id: int) -> bool:
        """
        Try to acquire a per-folder advisory transaction lock.

        Prevents concurrent writers (bootstrap/backfill/incremental) from
        mutating the same folder SSOT and cursor fields in parallel.
        """
        try:
            fid = int(folder_id or 0)
        except (TypeError, ValueError):
            return False
        if fid <= 0:
            return False
        lock_key = (self._folder_lock_namespace << 32) | (fid & 0xFFFFFFFF)
        self.env.cr.execute("SELECT pg_try_advisory_xact_lock(%s)", (int(lock_key),))
        row = self.env.cr.fetchone()
        return bool(row and row[0])

    # ------------------------------------------------------------------
    # IMAP helpers
    # ------------------------------------------------------------------

    def _select_folders_for_sync(self, account, limit=10):
        """
        Select MULTIPLE folders to sync using Two-Phase priority strategy.
        Throttles by COST (UID budget), not by entity count.

        Logic:
        1. Priority: folders marked dirty by Scan phase (needs_sync=True)
        2. Backfill: round-robin fallback to ensure liveness

        limit: Maximum folders to select (safety bound, not cost limit)
        """
        Folder = self.env["mailbox.folder"].sudo()

        # Priority 1: Dirty folders (needs_sync=True)
        folders = Folder.search(
            [
                ("account_id", "=", account.id),
                ("sync_state", "=", "incremental"),
                ("needs_sync", "=", True),
            ],
            order="last_sync_at ASC NULLS FIRST",
            limit=limit,
        )

        # Priority 2: Round-robin fallback (ensure no folder starves)
        if len(folders) < limit:
            already_selected_ids = folders.ids
            additional = Folder.search(
                [
                    ("account_id", "=", account.id),
                    ("sync_state", "=", "incremental"),
                    ("id", "not in", already_selected_ids),
                ],
                order="last_sync_at ASC NULLS FIRST",
                limit=limit - len(folders),
            )
            folders |= additional

        return folders

    def _open_client(self, account):
        return build_authenticated_imap_client(self.env, account)

    def _get_folder_status(self, client, folder_name: str) -> ImapFolderStatus:
        """Get IMAP status for any folder (not just INBOX)."""
        res = client.select_folder(folder_name, readonly=True) or {}
        uidvalidity = int(res.get(b"UIDVALIDITY", 0) or res.get("UIDVALIDITY", 0))
        uidnext = int(res.get(b"UIDNEXT", 1) or res.get("UIDNEXT", 1))
        highest_modseq = res.get(b"HIGHESTMODSEQ") or res.get("HIGHESTMODSEQ")
        try:
            highest_modseq = int(highest_modseq) if highest_modseq is not None else None
        except Exception:
            highest_modseq = None
        return ImapFolderStatus(
            uidvalidity=uidvalidity, uidnext=uidnext, highest_modseq=highest_modseq
        )

    def _sync_flags(
        self, client, account, folder, status: ImapFolderStatus, owner: str
    ) -> Optional[int]:
        folder_name = folder.imap_name or folder.name or "INBOX"
        supports_condstore = self._supports_condstore(client)
        if supports_condstore and status.highest_modseq is not None:
            last_modseq = int(folder.sync_modseq or "0")
            if last_modseq and status.highest_modseq <= last_modseq:
                return status.highest_modseq
            changed_uids = client.search(["MODSEQ", str(last_modseq or 0)]) or []
            self._update_flags(client, account, folder_name, changed_uids)
            return status.highest_modseq

        # Fallback: bounded batches over SEARCH ALL
        all_uids = client.search("ALL") or []
        for chunk in self._chunks(list(all_uids), self.flag_batch_size):
            self._update_flags(client, account, folder_name, chunk)
            self._renew_lease(account_id=account.id, owner=owner)
        return None

    def _supports_condstore(self, client) -> bool:
        try:
            caps = client.capabilities() or []
        except Exception:
            caps = []
        norm = {self._cap_to_text(c) for c in caps}
        return bool({"CONDSTORE", "QRESYNC"} & norm)

    def _cap_to_text(self, cap) -> str:
        if isinstance(cap, (bytes, bytearray)):
            return cap.decode("utf-8", "ignore").upper()
        return str(cap).upper()

    # ------------------------------------------------------------------
    # SSOT writes
    # ------------------------------------------------------------------

    def _fetch_message_batch(
        self, client, folder_name: str, account, uids: Sequence[int]
    ) -> List[Message]:
        if not uids:
            return []
        data = (
            client.fetch(
                list(uids),
                [
                    "ENVELOPE",
                    "FLAGS",
                    "UID",
                    "BODYSTRUCTURE",
                    "BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC MESSAGE-ID IN-REPLY-TO REFERENCES X-MAILDESK-OUTGOING-ID)]",
                    f"BODY.PEEK[]<0.{MAX_PREVIEW_BYTES}>",
                ],
            )
            or {}
        )
        messages: List[Message] = []
        for uid in uids:
            d = data.get(uid, {}) or {}
            msg = self._parse_message(uid, d, folder_name, account.id)
            if msg:
                messages.append(msg)
        return messages

    def _upsert_records(self, account, folder, messages: List[Message]):
        Index = self.env["maildesk.message_index"].sudo()
        enqueue = EnqueueIngestForMessageIndex(IngestQueueAdapter(self.env))

        new_uids = []
        inserted_index_ids = []
        message_summaries = []  # Realtime notification payload (gated in infrastructure)
        folder_name = folder.imap_name
        reconciled_moves: Dict[Tuple[str, str], List[str]] = {}
        reconciled_refresh_folders: Set[str] = set()

        for msg in messages:
            flags = self._flags_from_state(msg.is_read, msg.is_starred)

            provider_data = {
                "message_id": msg.message_header_id,
                "outgoing_id": msg.outgoing_id,
                "from_addr": msg.email_from,
                "to_addrs": msg.to_display,
                "cc_addrs": msg.cc_display,
                "bcc_addrs": msg.bcc_display,
                "subject": msg.subject,
                "date": msg.date,
                "sender_display_name": msg.sender_display_name,
                "preview": msg.snippet,
                "has_attachments": msg.has_attachments,
                "is_read": msg.is_read,
                "is_starred": msg.is_starred,
                "flags": flags,
                "in_reply_to": msg.in_reply_to,
                "references_hdr": msg.references,
                "thread_id": msg.thread_id,
            }

            # Outbound reconciliation (primary): outgoing_id (X-MailDesk-Outgoing-ID)
            if msg.outgoing_id:
                pending = Index.search(
                    [
                        ("account_id", "=", account.id),
                        ("provider", "=", "imap"),
                        ("local_pending", "=", True),
                        ("outgoing_id", "=", msg.outgoing_id),
                    ],
                    limit=2,
                )
                old_folder = str(pending[0].folder or "") if len(pending) == 1 else ""
                old_uid = str(pending[0].uid or "") if len(pending) == 1 else ""

                if Index.confirm_outbound_delivery(
                    account_id=account.id,
                    outgoing_id=msg.outgoing_id,
                    provider="imap",
                    provider_uid=str(msg.id),
                    provider_folder=folder_name,
                    provider_message_data=provider_data,
                ):
                    _logger.info(
                        "[IMAP Sync] Confirmed outbound delivery via outgoing_id=%s uid=%s",
                        msg.outgoing_id,
                        msg.id,
                    )

                    if old_folder and old_folder != folder_name:
                        reconciled_moves.setdefault(
                            (old_folder, folder_name), []
                        ).append(old_uid or str(msg.id))
                    else:
                        reconciled_refresh_folders.add(folder_name)

                    if len(pending) == 1:
                        try:
                            enqueue.execute(
                                EnqueueIngestForMessageIndexParams(
                                    index_id=pending[0].id, priority=10
                                )
                            )
                        except Exception as e:
                            _logger.warning(
                                "Failed to ingest confirmed outbound message %s: %s",
                                msg.id,
                                e,
                            )
                    continue

                touched = Index.touch_existing_outgoing_delivery(
                    account_id=account.id,
                    provider="imap",
                    provider_folder=folder_name,
                    outgoing_id=msg.outgoing_id,
                    provider_message_data=provider_data,
                )
                if touched:
                    # Avoid creating additional duplicates for the same outgoing_id.
                    continue

            # Fallback: Message-ID confirmation for local_pending (strict guards inside model method).
            if msg.message_header_id:
                if Index.confirm_outbound_delivery_by_message_id(
                    account_id=account.id,
                    provider="imap",
                    provider_uid=str(msg.id),
                    provider_folder=folder_name,
                    message_id=msg.message_header_id,
                    message_from=msg.email_from,
                    provider_message_data=provider_data,
                ):
                    reconciled_refresh_folders.add(folder_name)

                    # Best-effort ingest enqueue: locate confirmed row by its new triplet.
                    confirmed = Index.search(
                        [
                            ("account_id", "=", account.id),
                            ("provider", "=", "imap"),
                            ("folder", "=", folder_name),
                            ("uid", "=", str(msg.id)),
                        ],
                        limit=1,
                    )
                    if confirmed:
                        confirmed.write({"ingest_allowed": True})
                        try:
                            enqueue.execute(
                                EnqueueIngestForMessageIndexParams(
                                    index_id=confirmed.id, priority=10
                                )
                            )
                        except Exception as e:
                            _logger.warning(
                                "Failed to ingest confirmed (Message-ID fallback) message %s: %s",
                                msg.id,
                                e,
                            )
                    continue

            # Otherwise, normal upsert logic
            index_id, inserted = Index.upsert_one_with_inserted(
                {
                    "account_id": account.id,
                    "provider": "imap",
                    "folder": folder_name,
                    "uid": str(msg.id),
                    "ingest_allowed": True,
                    "message_id": msg.message_header_id,
                    "outgoing_id": msg.outgoing_id,
                    "from_addr": msg.email_from,
                    "to_addrs": msg.to_display,
                    "cc_addrs": msg.cc_display,
                    "bcc_addrs": msg.bcc_display,
                    "subject": msg.subject,
                    "date": msg.date,
                    "sender_display_name": msg.sender_display_name,
                    "preview": msg.snippet,
                    "has_attachments": msg.has_attachments,
                    "is_read": msg.is_read,
                    "is_starred": msg.is_starred,
                    "flags": flags,
                    "in_reply_to": msg.in_reply_to,
                    "references_hdr": msg.references,
                    "thread_id": msg.thread_id,
                }
            )
            if index_id and inserted:
                inserted_index_ids.append(int(index_id))
                new_uids.append(str(msg.id))

                # Build notification summary (minimal DTO for frontend)
                message_summaries.append(
                    {
                        "index_id": int(index_id),
                        "message_id": msg.message_header_id,
                        "account_id": int(account.id),
                        "account_display": account.name or account.email,
                        "folder": folder_name,
                        "uid": str(msg.id),
                        "subject": msg.subject or "(no subject)",
                        "preview": msg.snippet or "",
                        "sender_name": msg.sender_display_name
                        or msg.email_from
                        or "Unknown",
                        "from_email": msg.email_from or "",
                        "date": msg.date.isoformat() if msg.date else None,
                        "is_read": msg.is_read,
                        "is_starred": msg.is_starred,
                    }
                )

                # Queue for ingestion
                try:
                    enqueue.execute(
                        EnqueueIngestForMessageIndexParams(index_id=index_id)
                    )
                except Exception as e:
                    _logger.error(
                        "Failed to enqueue ingest for index_id=%s account_id=%s: %s",
                        index_id,
                        account.id,
                        e,
                        exc_info=True,
                    )

        # Avoid redundant refresh if this folder already has a messages_added event.
        if new_uids and folder_name in reconciled_refresh_folders:
            reconciled_refresh_folders.remove(folder_name)

        # Emit reconciliation notifications (must happen even when no new_uids were inserted).
        if self.notifier:
            for (source_folder, dest_folder), uids in reconciled_moves.items():
                if uids:
                    self.notifier.notify_messages_moved(
                        account_id=account.id,
                        source_folder=source_folder,
                        destination_folder=dest_folder,
                        uids=uids,
                    )
            for refresh_folder in sorted({f for f in reconciled_refresh_folders if f}):
                self.notifier.notify_full_refresh(
                    account_id=account.id,
                    folder=refresh_folder,
                )

        # Update unread counts for any folder affected by SSOT mutations in this batch.
        affected_folders: Set[str] = set()
        if new_uids:
            affected_folders.add(folder_name)
        affected_folders |= set(reconciled_refresh_folders)
        for source_folder, dest_folder in reconciled_moves.keys():
            if source_folder:
                affected_folders.add(source_folder)
            if dest_folder:
                affected_folders.add(dest_folder)

        if new_uids:
            # 1. Notify SSOT change (desktop notifications are gated in infrastructure)
            if self.notifier:
                self.notifier.notify_messages_added(
                    account_id=account.id,
                    folder=folder_name,
                    uids=new_uids,
                    origin="imap_incremental",
                    index_ids=inserted_index_ids,
                    messages=message_summaries,
                )

        for affected_folder_name in sorted({f for f in affected_folders if f}):
            folder_rec = folder if affected_folder_name == folder_name else None
            if not folder_rec:
                Folder = self.env["mailbox.folder"].sudo()
                folder_rec = Folder.search(
                    [
                        ("account_id", "=", account.id),
                        "|",
                        ("imap_name", "=", affected_folder_name),
                        ("name", "=", affected_folder_name),
                    ],
                    limit=1,
                )
            if not folder_rec:
                continue

            unread_count = Index.search_count(
                [
                    ("account_id", "=", account.id),
                    ("provider", "=", "imap"),
                    ("folder", "=", affected_folder_name),
                    ("is_read", "=", False),
                ]
            )
            if folder_rec.unread_count != unread_count:
                folder_rec.sudo().write(
                    {
                        "unread_count": unread_count,
                        "unread_count_updated_at": self.env.cr.now(),
                    }
                )
                if self.notifier:
                    self.notifier.notify_unread_count_changed(
                        account.id, affected_folder_name, unread_count
                    )

        return len(new_uids)

    def _update_flags(self, client, account, folder_name: str, uids: Sequence[int]):
        """
        Update message flags in SSOT from IMAP server state.
        Uses bulk processing to minimize DB transactions and concurrent updates.
        """
        if not uids:
            return

        data = client.fetch(list(uids), ["FLAGS"]) or {}
        Index = self.env["maildesk.message_index"].sudo()

        # 1. Fetch current SSOT records in bulk
        records = Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", folder_name),
                ("uid", "in", [str(u) for u in uids]),
            ]
        )
        uid_to_rec = {rec.uid: rec for rec in records}

        # 2. Group updates by flag state to minimize write calls
        updates = {}  # (is_read, is_starred, flags_str) -> List[Record]

        for uid, d in (data or {}).items():
            uid_str = str(uid)
            rec = uid_to_rec.get(uid_str)
            if not rec:
                continue

            flags_list = d.get(b"FLAGS") or d.get("FLAGS") or []
            imap_flags = MailFlags.from_imap_flags(flags_list)
            flags_str = self._flags_from_list(flags_list)

            # Skip if already in sync
            if (
                rec.is_read == imap_flags.is_read
                and rec.is_starred == imap_flags.is_starred
            ):
                continue

            state_key = (imap_flags.is_read, imap_flags.is_starred, flags_str)
            if state_key not in updates:
                updates[state_key] = Index.browse([])
            updates[state_key] |= rec

        # 3. Perform bulk writes
        updated_records = Index.browse([])
        for (is_read, is_starred, flags_str), subset in updates.items():
            subset.write(
                {
                    "is_read": is_read,
                    "is_starred": is_starred,
                    "flags": flags_str,
                }
            )
            updated_records |= subset

        # Emit bus event from SSOT (not from IMAP deltas).
        # Group records by identical flag state for efficient batching
        if updated_records:
            # Invalidate cache to ensure fresh read
            updated_records.invalidate_recordset(["is_read", "is_starred"])

            # Group by flag state for batching
            flag_groups = {}
            for rec in updated_records:
                # Validation: SSOT must never have None flags.
                if rec.is_read is None or rec.is_starred is None:
                    _logger.error(
                        f"SSOT VIOLATION: record {rec.id} has None flags! "
                        f"is_read={rec.is_read}, is_starred={rec.is_starred}"
                    )
                    continue

                # Read actual state from DB (SSOT).
                flag_key = (rec.is_read, rec.is_starred)
                if flag_key not in flag_groups:
                    flag_groups[flag_key] = {"uids": [], "index_ids": []}
                flag_groups[flag_key]["uids"].append(rec.uid)
                flag_groups[flag_key]["index_ids"].append(rec.id)

            # Emit one event per unique flag combination
            for (is_read, is_starred), group in flag_groups.items():
                self.notifier.notify_flags_changed(
                    account_id=account.id,
                    folder=folder_name,
                    uids=group["uids"],
                    index_ids=group["index_ids"],
                    is_read=is_read,
                    is_starred=is_starred,
                )

    def _reset_uidvalidity(self, account, folder, folder_name: str, uidvalidity: int):
        self.env.cr.execute(
            """
            DELETE FROM maildesk_message_index
            WHERE account_id = %s AND provider = 'imap' AND folder = %s
            """,
            (account.id, folder_name),
        )
        folder.write(
            {"uid_validity": int(uidvalidity or 0), "last_uid": 0, "sync_modseq": "0"}
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_message(self, uid: int, d: Dict, folder_name: str, account_id: int):
        env = d.get(b"ENVELOPE") or d.get("ENVELOPE")
        flags = d.get(b"FLAGS") or d.get("FLAGS") or []
        hdr_bytes = (
            d.get(
                b"BODY[HEADER.FIELDS (SUBJECT FROM TO CC MESSAGE-ID IN-REPLY-TO REFERENCES X-MAILDESK-OUTGOING-ID)]",
                b"",
            )
            or d.get(
                b"BODY[HEADER.FIELDS (SUBJECT FROM TO CC MESSAGE-ID IN-REPLY-TO REFERENCES)]",
                b"",
            )
            or b""
        )
        hdr_msg = BytesParser(policy=policy.default).parsebytes(hdr_bytes or b"")

        subject_raw = str(hdr_msg.get("Subject") or "")
        from_raw = str(hdr_msg.get("From") or "")
        raw_msgid = str(hdr_msg.get("Message-ID") or "")
        raw_irt = str(hdr_msg.get("In-Reply-To") or "")
        raw_refs = str(hdr_msg.get("References") or "")
        outgoing_id = str(hdr_msg.get("X-MailDesk-Outgoing-ID") or "").strip()

        sender_email = ""
        sender_name = ""
        if from_raw:
            parsed = parse_sender_header(from_raw.strip())
            sender_name = parsed[1]
            sender_email = parsed[2]

        subject = decode_header_value(subject_raw) or "(no subject)"
        msg_date = self._to_datetime(getattr(env, "date", None) if env else None)
        to_disp = self._join_addresses(getattr(env, "to", None) if env else None)
        cc_disp = self._join_addresses(getattr(env, "cc", None) if env else None)

        message_id_hdr = msgid_header(raw_msgid)
        in_reply_hdr = msgid_header(raw_irt)
        references_hdr = " ".join(parse_msgid_list(raw_refs))

        first_ref = ""
        if references_hdr:
            refs = parse_msgid_list(references_hdr)
            if refs:
                first_ref = norm_msgid(refs[0])

        thread_id = first_ref or norm_msgid(in_reply_hdr) or norm_msgid(message_id_hdr)

        body_bytes = pick_imap_body_bytes(d)
        preview = self._extract_imap_preview(body_bytes, subject)
        bodystructure = d.get(b"BODYSTRUCTURE") or d.get("BODYSTRUCTURE")
        has_atts = has_attachments_from_bodystructure(bodystructure)

        is_read = self._flag_seen(flags)
        is_starred = self._flag_starred(flags)

        return Message(
            id=str(uid),
            thread_id=thread_id or str(uid),
            account_id=account_id,
            message_header_id=message_id_hdr,
            in_reply_to=in_reply_hdr,
            references=references_hdr,
            date=msg_date,
            subject=subject,
            email_from=(sender_email or "").lower(),
            sender_display_name=sender_name,
            to_display=to_disp,
            cc_display=cc_disp,
            bcc_display="",
            snippet=preview or "",
            outgoing_id=outgoing_id,
            folder_ids=[folder_name],
            is_read=is_read,
            is_starred=is_starred,
            has_attachments=has_atts,
            metadata={"imap_uid": uid},
        )

    def _flag_seen(self, flags: Iterable) -> bool:
        return any(f in flags for f in [b"\\Seen", b"\\seen", "\\Seen", "\\seen"])

    def _flag_starred(self, flags: Iterable) -> bool:
        return b"\\Flagged" in flags or "\\Flagged" in flags

    def _flags_from_state(self, is_read: bool, is_starred: bool) -> str:
        flags = []
        if is_read:
            flags.append("\\Seen")
        if is_starred:
            flags.append("\\Flagged")
        return " ".join(flags)

    def _flags_from_list(self, flags: Iterable) -> str:
        if not flags:
            return ""
        out = []
        for f in flags:
            if isinstance(f, (bytes, bytearray)):
                out.append(f.decode("utf-8", "ignore"))
            else:
                out.append(str(f))
        return " ".join(sorted({f for f in out if f}))

    def _join_addresses(self, addr_list) -> str:
        if not addr_list:
            return ""
        res = []
        for addr in addr_list:
            if isinstance(addr, (list, tuple)) and len(addr) >= 4:
                name = self._to_text(addr[0], decode=True)
                mailbox = self._to_text(addr[2], decode=False)
                host = self._to_text(addr[3], decode=False)
                email = ""
                if mailbox and host:
                    email = f"{mailbox}@{host}"
                elif mailbox:
                    email = mailbox
                elif host:
                    email = host
                if name and email:
                    res.append(f"{name} <{email}>")
                elif name:
                    res.append(name)
                elif email:
                    res.append(email)
            else:
                res.append(str(addr))
        return ", ".join([r for r in res if r])

    def _to_text(self, value, *, decode: bool) -> str:
        if value is None:
            return ""
        if isinstance(value, (bytes, bytearray)):
            try:
                text = value.decode("utf-8", "ignore")
            except Exception:
                text = value.decode("latin-1", "ignore")
        else:
            text = str(value)
        return decode_header_value(text) if decode else text

    def _to_datetime(self, value):
        if not value:
            return datetime(1970, 1, 1)
        if isinstance(value, datetime):
            dt = value
        else:
            dt = fields.Datetime.to_datetime(value)
        if getattr(dt, "tzinfo", None):
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _extract_imap_preview(self, body_bytes, subject):
        return extract_imap_preview(body_bytes, subject)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def _uid_chunks(self, start: int, end: int, size: int) -> Iterable[List[int]]:
        cur = int(start)
        while cur <= end:
            chunk_end = min(end, cur + size - 1)
            yield list(range(cur, chunk_end + 1))
            cur = chunk_end + 1

    def _chunks(self, items: List[int], size: int) -> Iterable[List[int]]:
        for i in range(0, len(items), size):
            yield items[i : i + size]

    def _record_error(self, account, folder, exc: Exception):
        """
        Record sync error on folder and account.

        CRITICAL: Uses separate savepoint to prevent concurrent update errors
        when multiple workers are syncing different folders of the same account.
        """
        msg = str(exc)
        backoff_at = fields.Datetime.now() + relativedelta(minutes=10)

        try:
            # Use separate savepoint for error recording
            # This prevents "current transaction is aborted" cascade
            with self.env.cr.savepoint():
                account.write({"backoff_until": backoff_at})
                folder.write({"last_error": msg})
                _logger.warning("IMAP sync error for account %s: %s", account.id, msg)
        except Exception as write_err:
            # If error recording fails, just log it - don't fail the whole sync
            _logger.error(
                f"Failed to record sync error for account {account.id}: {write_err}",
                exc_info=True,
            )

    def _renew_lease(self, account_id: int, owner: Optional[str]):
        try:
            self.env["maildesk.account_lease"].sudo().renew(
                account_id, ttl_seconds=self.lease_ttl_seconds, owner=owner
            )
        except Exception:
            return

    # ------------------------------------------------------------------
    # SSOT Reconciliation (Server-Side Delete Detection)
    # ------------------------------------------------------------------

    def _capture_ssot_state(self, account, folder_name: str) -> dict:
        """
        Capture current SSOT state before sync.

        Returns dict with UIDs currently in SSOT for this folder.
        Used to detect server-side deletions by comparing with provider state.
        """
        Index = self.env["maildesk.message_index"].sudo()
        records = Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", folder_name),
                (
                    "local_pending",
                    "=",
                    False,
                ),  # Exclude local_pending to avoid false-positive deletion.
            ]
        )

        ssot_uids = {rec.uid for rec in records}

        return {"uids": ssot_uids}

    def _capture_provider_state(self, client) -> dict:
        """
        Capture current provider state after sync.

        Returns dict with UIDs currently on IMAP server.
        Used to detect server-side deletions by comparing with SSOT state.
        """
        try:
            all_uids = client.search("ALL") or []
            provider_uids = {str(uid) for uid in all_uids}
            return {"uids": provider_uids}
        except Exception as e:
            _logger.warning(
                "[IMAP Sync] Failed to capture provider state for reconciliation: %s", e
            )
            return {"uids": set()}

    def _reconcile_and_emit(
        self, account, folder_name: str, ssot_before: dict, provider_after: dict
    ):
        """
        Reconcile SSOT vs provider to detect server-side deletions.

        Architecture:
        - Deletions: UIDs in SSOT but not on provider (EXPUNGE detected)
        - Emits domain event via SSotChangeNotifier
        - No direct bus calls (follows Clean Architecture)
        """
        ssot_uids = ssot_before["uids"]
        provider_uids = provider_after["uids"]

        # Detect deleted UIDs (present in SSOT, absent on provider)
        deleted_uids = ssot_uids - provider_uids

        if deleted_uids:
            _logger.info(
                f"[IMAP Sync] Detected server-side deletions: "
                f"account={account.id}, folder={folder_name}, count={len(deleted_uids)}"
            )

            # Update SSOT (remove deleted messages)
            self._apply_deletions(account, folder_name, list(deleted_uids))

            # Emit domain event via injected notifier.
            self.notifier.notify_messages_deleted(
                account_id=account.id, folder=folder_name, uids=list(deleted_uids)
            )

    def _apply_deletions(self, account, folder_name: str, deleted_uids: list):
        """
        Remove deleted messages from SSOT.

        Hard delete (unlink) is used as it's simpler and matches user expectation.
        Alternative would be soft delete with deleted_on_server flag.
        """
        Index = self.env["maildesk.message_index"].sudo()

        records = Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", folder_name),
                ("uid", "in", deleted_uids),
            ]
        )

        if records:
            count = len(records)
            records.unlink()
            _logger.info(
                f"[SSOT] Deleted {count} records from message_index: "
                f"account={account.id}, folder={folder_name}"
            )
