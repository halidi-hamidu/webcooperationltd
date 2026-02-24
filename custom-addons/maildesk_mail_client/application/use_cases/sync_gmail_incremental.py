# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Gmail Incremental Sync (History API)

Bounded, SSOT-first incremental sync for Gmail accounts.
Emits SSOT change notifications after SSOT writes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from dateutil.relativedelta import relativedelta
from googleapiclient.errors import HttpError
from odoo import fields

from ...adapters.gmail_adapter import GmailAdapter
from ...domain.contracts import Message
from ...infrastructure.adapters.ingest_queue_adapter import IngestQueueAdapter
from ...infrastructure.providers.gmail.auth import gmail_build_service
from ...infrastructure.utils.folder_keys import (
    expand_synonyms,
    keys_from_text,
    label_synonyms,
    normalize_folder_key,
)
from ...infrastructure.utils.email_utils import decode_header_value, parse_sender_header
from .ingest_queue import (
    EnqueueIngestForMessageIndex,
    EnqueueIngestForMessageIndexParams,
)

_logger = logging.getLogger(__name__)


class HistoryExpiredError(Exception):
    pass


@dataclass
class GmailHistoryResult:
    history_id: str
    messages_to_fetch: Set[str]
    new_message_ids: Set[str]
    deleted_ids: Set[str]
    labels_removed: Dict[str, Set[str]]
    truncated: bool = False


class SyncGmailIncremental:
    """
    Gmail History API incremental sync with SSOT notification parity.
    """

    def __init__(
        self,
        env,
        *,
        notifier,
        lease_ttl_seconds: int = 300,
        max_history_pages: int = 20,
        max_messages_per_run: int = 800,
    ):
        self.env = env
        self.notifier = notifier
        self.lease_ttl_seconds = lease_ttl_seconds
        self.max_history_pages = max_history_pages
        self.max_messages_per_run = max_messages_per_run

    def execute(self, account_id: int) -> dict:
        Account = self.env["mailbox.account"].sudo()
        account = Account.browse(int(account_id))
        if not account.exists() or not account.is_gmail:
            return {"ok": False, "reason": "not_gmail"}

        if account.backoff_until and account.backoff_until > fields.Datetime.now():
            return {"ok": False, "reason": "backoff"}

        Lease = self.env["maildesk.account_lease"].sudo()
        owner = f"gmail-incremental:{self.env.cr.dbname}:{account.id}"
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
        service = gmail_build_service(account)

        if not account.gmail_last_history_id or account.gmail_last_history_id == "0":
            return self._handle_history_expired(account, service, reason="bootstrap")

        try:
            result = self._incremental(account, service, owner)
            account.write(
                {
                    "gmail_last_sync_at": fields.Datetime.now(),
                    "gmail_last_error": False,
                    "backoff_until": False,
                }
            )
            return result
        except HistoryExpiredError:
            return self._handle_history_expired(
                account, service, reason="history_expired"
            )
        except Exception as e:
            self._record_error(account, e)
            return {"ok": False, "error": str(e)}

    def _incremental(self, account, service, owner: str) -> dict:
        start_id = str(account.gmail_last_history_id)
        hist = self._collect_history(
            service, start_id, owner, account.id, self.max_history_pages
        )

        label_id_map = self._get_label_id_map(service)
        folder_map = self._build_folder_map(account)

        messages_to_fetch = set(hist.messages_to_fetch) - set(hist.deleted_ids)
        messages = self._fetch_messages(service, account, messages_to_fetch)
        deleted_by_label = self._deleted_uids_from_labels(
            messages, label_id_map=label_id_map, folder_map=folder_map
        )
        if deleted_by_label:
            hist.deleted_ids.update(deleted_by_label)
            hist.new_message_ids.difference_update(deleted_by_label)
            messages = [m for m in messages if str(m.id) not in deleted_by_label]
            if hist.labels_removed:
                hist.labels_removed = {
                    mid: labels
                    for mid, labels in hist.labels_removed.items()
                    if str(mid) not in deleted_by_label
                }
        current_labels = self._current_label_names(messages, label_id_map)

        added_by_folder: Dict[str, Dict[str, List]] = {}
        flags_changed: Dict[str, Dict[Tuple[bool, bool], Dict[str, List]]] = {}
        deleted_by_folder: Dict[str, List[str]] = {}
        reconciled_refresh_folders: Set[str] = set()

        if messages:
            added_by_folder, flags_changed, reconciled_refresh_folders = (
                self._upsert_messages(
                    account,
                    messages,
                    label_id_map=label_id_map,
                    folder_map=folder_map,
                    add_all_mail=True,
                    deleted_by_folder=deleted_by_folder,
                    new_message_ids=hist.new_message_ids,
                )
            )

        if hist.labels_removed:
            removed = self._apply_label_removals(
                account,
                hist.labels_removed,
                label_id_map=label_id_map,
                folder_map=folder_map,
                current_labels=current_labels,
            )
            for folder_name, uids in removed.items():
                deleted_by_folder.setdefault(folder_name, []).extend(uids)

        if hist.deleted_ids:
            deleted = self._delete_messages(account, hist.deleted_ids)
            for folder_name, uids in deleted.items():
                deleted_by_folder.setdefault(folder_name, []).extend(uids)

        account.write({"gmail_last_history_id": hist.history_id})

        changes = bool(
            messages_to_fetch
            or hist.deleted_ids
            or hist.labels_removed
            or hist.truncated
        )

        if added_by_folder:
            self._touch_folders_last_sync_at(account, set(added_by_folder.keys()))

        self._emit_notifications(
            account,
            added_by_folder,
            flags_changed,
            deleted_by_folder,
            reconciled_refresh_folders,
        )

        return {
            "ok": True,
            "changes": changes,
            "history_id": hist.history_id,
            "fetched": len(messages_to_fetch),
            "deleted": len(hist.deleted_ids),
            "truncated": bool(hist.truncated),
            "new_count": sum(len(v.get("uids", [])) for v in added_by_folder.values()),
        }

    # ------------------------------------------------------------------
    # History collection
    # ------------------------------------------------------------------

    def _collect_history(
        self,
        service,
        start_id: str,
        owner: str,
        account_id: int,
        max_pages: int,
    ) -> GmailHistoryResult:
        messages_to_fetch: Set[str] = set()
        new_message_ids: Set[str] = set()
        deleted_ids: Set[str] = set()
        labels_removed: Dict[str, Set[str]] = {}

        page_token = None
        pages = 0
        truncated = False
        max_history_id: Optional[int] = None
        last_processed_id: Optional[str] = None
        response_history_id: Optional[str] = None

        while True:
            resp = self._history_list(service, start_id, page_token)
            response_history_id = resp.get("historyId") or response_history_id

            for item in resp.get("history", []) or []:
                item_id = item.get("id")
                if item_id:
                    try:
                        item_int = int(item_id)
                    except (TypeError, ValueError):
                        item_int = None
                    if item_int is not None:
                        if max_history_id is None or item_int > max_history_id:
                            max_history_id = item_int
                    else:
                        last_processed_id = str(item_id)

                for h in item.get("messagesAdded", []) or []:
                    mid = (h.get("message") or {}).get("id")
                    if mid:
                        messages_to_fetch.add(str(mid))
                        new_message_ids.add(str(mid))
                for h in item.get("labelsAdded", []) or []:
                    mid = (h.get("message") or {}).get("id")
                    if mid:
                        messages_to_fetch.add(str(mid))
                for h in item.get("labelsRemoved", []) or []:
                    mid = (h.get("message") or {}).get("id")
                    if not mid:
                        continue
                    messages_to_fetch.add(str(mid))
                    labels = h.get("labelIds") or []
                    labels_removed.setdefault(str(mid), set()).update(
                        {str(label) for label in labels}
                    )
                for h in item.get("messagesDeleted", []) or []:
                    mid = (h.get("message") or {}).get("id")
                    if mid:
                        deleted_ids.add(str(mid))

            pages += 1
            if pages >= max_pages:
                truncated = True
                break

            if (
                self.max_messages_per_run > 0
                and len(messages_to_fetch) >= self.max_messages_per_run
            ):
                truncated = True
                break

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

            self._renew_lease(account_id=account_id, owner=owner)

        if max_history_id is not None:
            history_id = str(max_history_id)
        elif last_processed_id:
            history_id = str(last_processed_id)
        elif response_history_id:
            history_id = str(response_history_id)
        else:
            history_id = str(start_id)

        return GmailHistoryResult(
            history_id=history_id,
            messages_to_fetch=messages_to_fetch,
            new_message_ids=new_message_ids,
            deleted_ids=deleted_ids,
            labels_removed=labels_removed,
            truncated=truncated,
        )

    def _history_list(self, service, start_id: str, page_token: Optional[str]):
        try:
            req = (
                service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=str(start_id),
                    historyTypes=[
                        "messageAdded",
                        "messageDeleted",
                        "labelAdded",
                        "labelRemoved",
                    ],
                    pageToken=page_token,
                    maxResults=500,
                )
            )
            return req.execute()
        except HttpError as e:
            if self._is_history_expired(e):
                raise HistoryExpiredError() from e
            raise

    # ------------------------------------------------------------------
    # SSOT write + enqueue
    # ------------------------------------------------------------------

    def _fetch_messages(
        self, service, account, message_ids: Iterable[str]
    ) -> List[Message]:
        ids = [str(m) for m in message_ids if m]
        if not ids:
            return []

        class Facade:
            def _decode_header_value(self, h):
                return decode_header_value(h)

            def _parse_sender_header(self, h):
                return parse_sender_header(h)

        adapter = GmailAdapter(Facade())
        return adapter.fetch_metadata_batch(service, account.id, "ALL_MAIL", ids)

    def _upsert_messages(
        self,
        account,
        messages: List[Message],
        *,
        label_id_map: Dict[str, str],
        folder_map: Dict[str, str],
        add_all_mail: bool,
        deleted_by_folder: Dict[str, List[str]],
        new_message_ids: Set[str],
    ) -> Tuple[
        Dict[str, Dict[str, List]], Dict[str, Dict[Tuple[bool, bool], Dict[str, List]]]
    ]:
        Index = self.env["maildesk.message_index"].sudo()
        enqueue = EnqueueIngestForMessageIndex(IngestQueueAdapter(self.env))

        added_by_folder: Dict[str, Dict[str, List]] = {}
        flags_changed: Dict[str, Dict[Tuple[bool, bool], Dict[str, List]]] = {}
        reconciled_refresh_folders: Set[str] = set()

        for msg in messages:
            label_ids = msg.metadata.get("label_ids") or []
            label_names = {
                label_id_map.get(str(lid))
                for lid in label_ids
                if str(lid) in label_id_map
            }
            label_names = {ln for ln in label_names if ln}

            folder_names: Set[str] = set()
            for name in label_names:
                f = self._folder_name_for_label(name, folder_map)
                if f:
                    folder_names.add(f)

            if add_all_mail and self._is_spam_or_trash(label_names):
                removed = Index.search(
                    [
                        ("account_id", "=", account.id),
                        ("provider", "=", "gmail"),
                        ("folder", "=", "ALL_MAIL"),
                        ("uid", "=", str(msg.id)),
                        ("local_pending", "=", False),
                    ]
                )
                if removed:
                    removed.unlink()
                    deleted_by_folder.setdefault("ALL_MAIL", []).append(str(msg.id))

            include_all_mail = add_all_mail and not self._is_spam_or_trash(label_names)
            if include_all_mail:
                folder_names.add("ALL_MAIL")

            if not folder_names:
                continue

            for folder_name in folder_names:
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
                            ("provider", "=", "gmail"),
                            ("local_pending", "=", True),
                            ("outgoing_id", "=", msg.outgoing_id),
                        ],
                        limit=2,
                    )
                    old_folder = (
                        str(pending[0].folder or "") if len(pending) == 1 else ""
                    )

                    if Index.confirm_outbound_delivery(
                        account_id=account.id,
                        outgoing_id=msg.outgoing_id,
                        provider="gmail",
                        provider_uid=str(msg.id),
                        provider_folder=folder_name,
                        provider_message_data=provider_data,
                    ):
                        reconciled_refresh_folders.add(str(old_folder or folder_name))
                        reconciled_refresh_folders.add(str(folder_name or old_folder))
                        if len(pending) == 1:
                            try:
                                enqueue.execute(
                                    EnqueueIngestForMessageIndexParams(
                                        index_id=pending[0].id, priority=10
                                    )
                                )
                            except Exception:
                                _logger.debug(
                                    "Failed to enqueue ingest for confirmed gmail outgoing %s",
                                    msg.id,
                                    exc_info=True,
                                )
                        continue

                    touched = Index.touch_existing_outgoing_delivery(
                        account_id=account.id,
                        provider="gmail",
                        provider_folder=folder_name,
                        outgoing_id=msg.outgoing_id,
                        provider_message_data=provider_data,
                    )
                    if touched:
                        continue

                # Fallback: Message-ID confirmation for local_pending (strict guards inside model method).
                if (not msg.outgoing_id) and msg.message_header_id:
                    if Index.confirm_outbound_delivery_by_message_id(
                        account_id=account.id,
                        provider="gmail",
                        provider_uid=str(msg.id),
                        provider_folder=folder_name,
                        message_id=msg.message_header_id,
                        message_from=msg.email_from,
                        provider_message_data=provider_data,
                    ):
                        reconciled_refresh_folders.add(str(folder_name))
                        confirmed = Index.search(
                            [
                                ("account_id", "=", account.id),
                                ("provider", "=", "gmail"),
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
                            except Exception:
                                _logger.debug(
                                    "Failed to enqueue ingest for confirmed gmail (Message-ID fallback) %s",
                                    msg.id,
                                    exc_info=True,
                                )
                        continue

                existing = Index.search(
                    [
                        ("account_id", "=", account.id),
                        ("provider", "=", "gmail"),
                        ("folder", "=", folder_name),
                        ("uid", "=", str(msg.id)),
                    ],
                    limit=1,
                )
                old_is_read = existing.is_read if existing else None
                old_is_starred = existing.is_starred if existing else None

                index_id, inserted = Index.upsert_one_with_inserted(
                    {
                        "account_id": account.id,
                        "provider": "gmail",
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
                        "deleted_on_server": False,
                    }
                )

                # Threading reconciliation: if this is a reply and Gmail provided a threadId,
                # propagate that threadId onto the parent SSOT row(s) referenced by In-Reply-To.
                # This fixes the case where SSOT-on-send used Message-ID-derived thread_id
                # until the provider threadId becomes known.
                if msg.thread_id and msg.in_reply_to:
                    try:
                        Index.reconcile_thread_id_from_reply(
                            account_id=account.id,
                            provider="gmail",
                            thread_id=msg.thread_id,
                            in_reply_to=msg.in_reply_to,
                        )
                    except Exception:
                        _logger.debug(
                            "Thread reconciliation failed for gmail reply uid=%s",
                            msg.id,
                            exc_info=True,
                        )

                if index_id and inserted:
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

                if inserted:
                    added = added_by_folder.setdefault(
                        folder_name,
                        {"uids": [], "index_ids": [], "messages": []},
                    )
                    added["uids"].append(str(msg.id))
                    if str(msg.id) in new_message_ids:
                        added["index_ids"].append(int(index_id))
                        added["messages"].append(
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
                else:
                    if (
                        old_is_read is not None
                        and old_is_starred is not None
                        and (
                            old_is_read != msg.is_read
                            or old_is_starred != msg.is_starred
                        )
                    ):
                        state_key = (msg.is_read, msg.is_starred)
                        flags_changed.setdefault(folder_name, {}).setdefault(
                            state_key, {"uids": [], "index_ids": []}
                        )
                        flags_changed[folder_name][state_key]["uids"].append(
                            str(msg.id)
                        )
                        flags_changed[folder_name][state_key]["index_ids"].append(
                            int(index_id)
                        )

        return added_by_folder, flags_changed, reconciled_refresh_folders

    def _apply_label_removals(
        self,
        account,
        labels_removed: Dict[str, Set[str]],
        *,
        label_id_map: Dict[str, str],
        folder_map: Dict[str, str],
        current_labels: Dict[str, Set[str]],
    ) -> Dict[str, List[str]]:
        Index = self.env["maildesk.message_index"].sudo()
        removed_by_folder: Dict[str, List[str]] = {}

        for mid, label_ids in labels_removed.items():
            present = current_labels.get(str(mid), set())
            label_names = [
                label_id_map.get(str(lid))
                for lid in label_ids
                if str(lid) in label_id_map
            ]
            for name in label_names:
                if not name or name in present:
                    continue
                folder_name = self._folder_name_for_label(name, folder_map)
                if not folder_name:
                    continue
                recs = Index.search(
                    [
                        ("account_id", "=", account.id),
                        ("provider", "=", "gmail"),
                        ("folder", "=", folder_name),
                        ("uid", "=", str(mid)),
                        ("local_pending", "=", False),
                    ]
                )
                if recs:
                    recs.unlink()
                    removed_by_folder.setdefault(folder_name, []).append(str(mid))

        return removed_by_folder

    def _delete_messages(
        self, account, message_ids: Iterable[str]
    ) -> Dict[str, List[str]]:
        ids = [str(x) for x in message_ids if x]
        if not ids:
            return {}
        Index = self.env["maildesk.message_index"].sudo()
        recs = Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "gmail"),
                ("uid", "in", ids),
                ("local_pending", "=", False),
            ]
        )
        deleted_by_folder: Dict[str, List[str]] = {}
        for rec in recs:
            deleted_by_folder.setdefault(rec.folder, []).append(rec.uid)
        if recs:
            recs.unlink()
        return deleted_by_folder

    # ------------------------------------------------------------------
    # Notifications + unread counts
    # ------------------------------------------------------------------

    def _emit_notifications(
        self,
        account,
        added_by_folder: Dict[str, Dict[str, List]],
        flags_changed: Dict[str, Dict[Tuple[bool, bool], Dict[str, List]]],
        deleted_by_folder: Dict[str, List[str]],
        refresh_folders: Optional[Set[str]] = None,
    ) -> None:
        if not self.notifier:
            return

        affected_folders: Set[str] = set()
        refreshed_by_list_events: Set[str] = set()

        for folder_name, data in added_by_folder.items():
            uids = data.get("uids") or []
            if not uids:
                continue
            self.notifier.notify_messages_added(
                account_id=account.id,
                folder=folder_name,
                uids=uids,
                origin="gmail_incremental",
                index_ids=data.get("index_ids") or [],
                messages=data.get("messages") or [],
            )
            affected_folders.add(folder_name)
            refreshed_by_list_events.add(folder_name)

        for folder_name, grouped in flags_changed.items():
            for (is_read, is_starred), group in grouped.items():
                uids = group.get("uids") or []
                if not uids:
                    continue
                self.notifier.notify_flags_changed(
                    account_id=account.id,
                    folder=folder_name,
                    uids=uids,
                    index_ids=group.get("index_ids") or [],
                    is_read=is_read,
                    is_starred=is_starred,
                )
                affected_folders.add(folder_name)

        for folder_name, uids in deleted_by_folder.items():
            if not uids:
                continue
            self.notifier.notify_messages_deleted(
                account_id=account.id,
                folder=folder_name,
                uids=uids,
            )
            affected_folders.add(folder_name)
            refreshed_by_list_events.add(folder_name)

        for folder_name in sorted({f for f in (refresh_folders or set()) if f}):
            # Avoid redundant refresh if a list-affecting event already triggers a refresh.
            if folder_name in refreshed_by_list_events:
                continue
            self.notifier.notify_full_refresh(account_id=account.id, folder=folder_name)
            affected_folders.add(folder_name)

        for folder_name in sorted(affected_folders):
            self._refresh_unread_count(account, folder_name)

    def _refresh_unread_count(self, account, folder_name: str) -> None:
        Folder = self.env["mailbox.folder"].sudo()
        folder = Folder.search(
            [
                ("account_id", "=", account.id),
                "|",
                ("imap_name", "=", folder_name),
                ("name", "=", folder_name),
            ],
            limit=1,
        )
        if not folder:
            return

        Index = self.env["maildesk.message_index"].sudo()
        unread_count = Index.search_count(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "gmail"),
                ("folder", "=", folder_name),
                ("is_read", "=", False),
            ]
        )

        if folder.unread_count != unread_count:
            folder.write(
                {
                    "unread_count": unread_count,
                    "unread_count_updated_at": self.env.cr.now(),
                }
            )
            self.notifier.notify_unread_count_changed(
                account.id, folder_name, unread_count
            )

    def _touch_folders_last_sync_at(self, account, folder_names: Set[str]) -> None:
        if not folder_names:
            return
        Folder = self.env["mailbox.folder"].sudo()
        now = fields.Datetime.now()
        for folder_name in sorted({f for f in folder_names if f}):
            folder = Folder.search(
                [
                    ("account_id", "=", account.id),
                    "|",
                    ("imap_name", "=", folder_name),
                    ("name", "=", folder_name),
                ],
                limit=1,
            )
            if folder:
                folder.write({"last_sync_at": now})

    # ------------------------------------------------------------------
    # Mapping helpers
    # ------------------------------------------------------------------

    def _get_label_id_map(self, service) -> Dict[str, str]:
        resp = service.users().labels().list(userId="me").execute()
        labels = resp.get("labels") or []
        return {
            str(label["id"]): str(label["name"]) for label in labels if label.get("id")
        }

    def _build_folder_map(self, account) -> Dict[str, str]:
        Folder = self.env["mailbox.folder"].sudo()
        folders = Folder.search([("account_id", "=", account.id)])
        mapping: Dict[str, str] = {}
        for f in folders:
            for key in self._folder_keys(f.name) | self._folder_keys(f.imap_name):
                mapping[key] = f.imap_name or f.name
        return mapping

    def _folder_name_for_label(
        self, label_name: str, folder_map: Dict[str, str]
    ) -> Optional[str]:
        if not label_name:
            return None
        key = normalize_folder_key(label_name)
        acceptable = expand_synonyms({key})
        for cand in [key] + sorted(acceptable - {key}):
            if cand in folder_map:
                return folder_map[cand]
        return None

    def _label_synonyms(self) -> Dict[str, List[str]]:
        return label_synonyms()

    def _is_spam_or_trash(self, label_names: Iterable[str]) -> bool:
        keys = {normalize_folder_key(x) for x in label_names if x}
        return bool(keys & {"spam", "trash"})

    def _norm(self, text: Optional[str]) -> str:
        return normalize_folder_key(text)

    def _folder_keys(self, text: Optional[str]) -> Set[str]:
        return keys_from_text(text)

    def _flags_from_state(self, is_read: bool, is_starred: bool) -> str:
        flags = []
        if is_read:
            flags.append("\\Seen")
        if is_starred:
            flags.append("\\Flagged")
        return " ".join(flags)

    def _current_label_names(
        self, messages: List[Message], label_id_map: Dict[str, str]
    ) -> Dict[str, Set[str]]:
        current: Dict[str, Set[str]] = {}
        for msg in messages or []:
            label_ids = msg.metadata.get("label_ids") or []
            label_names = {
                label_id_map.get(str(lid))
                for lid in label_ids
                if str(lid) in label_id_map
            }
            label_names = {ln for ln in label_names if ln}
            current[str(msg.id)] = label_names
        return current

    def _deleted_uids_from_labels(
        self,
        messages: List[Message],
        *,
        label_id_map: Dict[str, str],
        folder_map: Dict[str, str],
    ) -> Set[str]:
        deleted: Set[str] = set()
        for msg in messages or []:
            label_ids = msg.metadata.get("label_ids") or []
            label_names = {
                label_id_map.get(str(lid))
                for lid in label_ids
                if str(lid) in label_id_map
            }
            label_names = {ln for ln in label_names if ln}
            if self._should_treat_as_deleted(label_names, folder_map):
                deleted.add(str(msg.id))
        return deleted

    def _should_treat_as_deleted(
        self, label_names: Set[str], folder_map: Dict[str, str]
    ) -> bool:
        if not label_names:
            return True
        normed = {self._norm(n) for n in label_names if n}
        if "trash" in normed:
            return True
        for name in label_names:
            if not name:
                continue
            if self._folder_name_for_label(name, folder_map):
                if self._norm(name) != "trash":
                    return False
        return True

    # ------------------------------------------------------------------
    # History expiration recovery
    # ------------------------------------------------------------------

    def _handle_history_expired(self, account, service, reason: str) -> dict:
        base_history_id = self._get_profile_history_id(service)
        account.write(
            {
                "gmail_last_history_id": base_history_id,
                "gmail_last_sync_at": fields.Datetime.now(),
                "gmail_last_error": False,
                "backoff_until": False,
            }
        )

        folders = (
            self.env["mailbox.folder"].sudo().search([("account_id", "=", account.id)])
        )
        for folder in folders:
            vals = {
                "sync_state": "backfill_pending",
                "last_uid": 0,
                "backfill_last_uid": 0,
                "backfill_fetched_count": 0,
                "backfill_total_estimate": 0,
                "backfill_started_at": False,
                "backfill_completed_at": False,
            }
            if "gmail_backfill_page_token" in folder._fields:
                vals["gmail_backfill_page_token"] = False
            if "gmail_label_id" in folder._fields:
                vals["gmail_label_id"] = False
            folder.write(vals)

        if self.notifier:
            self.notifier.notify_full_refresh(account_id=account.id, folder=None)

        return {"ok": True, "mode": reason, "changes": True}

    def _get_profile_history_id(self, service) -> str:
        profile = service.users().getProfile(userId="me").execute()
        return str(profile.get("historyId") or "0")

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def _is_history_expired(self, exc: HttpError) -> bool:
        try:
            status = getattr(exc, "status_code", None) or exc.resp.status
        except Exception:
            status = None
        if status == 404:
            return True
        if status == 400:
            try:
                body = exc.content.decode("utf-8", "ignore") if exc.content else ""
            except Exception:
                body = ""
            if "HistoryId" in body or "historyId" in body:
                return True
        return False

    def _record_error(self, account, exc: Exception):
        msg = str(exc)
        backoff_at = fields.Datetime.now() + relativedelta(minutes=10)
        account.write(
            {
                "gmail_last_error": msg,
                "backoff_until": backoff_at,
            }
        )
        _logger.warning("Gmail sync error for account %s: %s", account.id, msg)

    def _renew_lease(self, account_id: int, owner: str):
        try:
            self.env["maildesk.account_lease"].sudo().renew(
                account_id, ttl_seconds=self.lease_ttl_seconds, owner=owner
            )
        except Exception:
            return
