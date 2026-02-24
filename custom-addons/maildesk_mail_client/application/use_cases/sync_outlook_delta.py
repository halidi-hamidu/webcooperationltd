# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Outlook Incremental Sync (Graph Delta)

Bounded, SSOT-first incremental sync for Outlook accounts.
Emits SSOT change notifications after SSOT writes.
"""

from __future__ import annotations

import logging
import psycopg2
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple

from dateutil.relativedelta import relativedelta
from odoo import fields

from ...domain.contracts import Message
from ...domain.services.normalization import msgid_header
from ...infrastructure.adapters.ingest_queue_adapter import IngestQueueAdapter
from ...infrastructure.providers.outlook.client_factory import get_outlook_client
from .ingest_queue import (
    EnqueueIngestForMessageIndex,
    EnqueueIngestForMessageIndexParams,
)

_logger = logging.getLogger(__name__)


class DeltaExpiredError(Exception):
    pass


@dataclass
class OutlookFolderDeltaResult:
    cursor: str
    initialized: bool
    removed_ids: List[str]
    processed_items: int
    pages_used: int
    truncated: bool = False


class SyncOutlookDelta:
    """
    Outlook Graph delta incremental sync with SSOT notification parity.
    """

    def __init__(
        self,
        env,
        *,
        notifier,
        lease_ttl_seconds: int = 300,
        max_pages: int = 20,
        max_items_per_run: int = 800,
    ):
        self.env = env
        self.notifier = notifier
        self.lease_ttl_seconds = lease_ttl_seconds
        self.max_pages = max_pages
        self.max_items_per_run = max_items_per_run

    def execute(self, account_id: int) -> dict:
        Account = self.env["mailbox.account"].sudo()
        account = Account.browse(int(account_id))
        if not account.exists() or not account.is_outlook:
            return {"ok": False, "reason": "not_outlook"}

        if account.backoff_until and account.backoff_until > fields.Datetime.now():
            return {"ok": False, "reason": "backoff"}

        Lease = self.env["maildesk.account_lease"].sudo()
        owner = f"outlook-delta:{self.env.cr.dbname}:{account.id}"
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
        sess, base_url = get_outlook_client(self.env, account)
        if not sess or not base_url:
            return {"ok": False, "reason": "outlook_session_failed"}

        folder_map = self._build_folder_map(account)
        if not folder_map:
            return {"ok": True, "mode": "no_folders", "changes": False}

        try:
            result = self._incremental(account, sess, base_url, owner, folder_map)
            account.write({"backoff_until": False})
            return result
        except DeltaExpiredError:
            return self._handle_delta_expired(account)
        except Exception as e:
            self._record_error(account, e)
            return {"ok": False, "error": str(e)}

    def _incremental(
        self, account, sess, base_url: str, owner: str, folder_map: Dict[str, str]
    ) -> dict:
        added_by_folder: Dict[str, Dict[str, List]] = {}
        flags_changed: Dict[str, Dict[Tuple[bool, bool], Dict[str, List]]] = {}
        deleted_by_folder: Dict[str, List[str]] = {}
        moved_by_folder: Dict[Tuple[str, str], List[str]] = {}
        refresh_folders: Set[str] = set()
        removed_candidates: List[Tuple[str, str]] = []

        tokens = self._get_delta_tokens(account)
        folder_states = tokens.get("message_delta_by_folder") or {}
        if not isinstance(folder_states, dict):
            folder_states = {}

        processed_total = 0
        truncated = False
        pages_total = 0

        for folder_graph_id, folder_name in self._folders_for_delta(folder_map):
            state = folder_states.get(folder_graph_id) or {}
            if not isinstance(state, dict):
                state = {}

            cursor = str(state.get("cursor") or "").strip()
            initialized = bool(state.get("initialized"))
            if not cursor:
                cursor = self._initial_delta_url(base_url, folder_graph_id)
                initialized = False

            res = self._collect_folder_delta(
                account=account,
                sess=sess,
                cursor=cursor,
                owner=owner,
                folder_name=folder_name,
                initialized=initialized,
                added_by_folder=added_by_folder,
                flags_changed=flags_changed,
                moved_by_folder=moved_by_folder,
                refresh_folders=refresh_folders,
                processed_already=processed_total,
                pages_left=(
                    max(self.max_pages - pages_total, 0) if self.max_pages > 0 else 0
                ),
            )

            folder_states[folder_graph_id] = {
                "cursor": res.cursor,
                "initialized": res.initialized,
            }
            removed_candidates.extend([(folder_name, mid) for mid in res.removed_ids])
            processed_total += int(res.processed_items or 0)
            pages_total += int(res.pages_used or 0)

            if res.truncated:
                truncated = True

            if self.max_pages > 0 and pages_total >= self.max_pages:
                truncated = True
                break

            if self.max_items_per_run > 0 and processed_total >= self.max_items_per_run:
                truncated = True
                break

            self._renew_lease(account_id=account.id, owner=owner)

        if removed_candidates:
            self._resolve_removed_candidates(
                account=account,
                sess=sess,
                base_url=base_url,
                folder_map=folder_map,
                removed_candidates=removed_candidates,
                deleted_by_folder=deleted_by_folder,
                moved_by_folder=moved_by_folder,
            )

        tokens["message_delta_by_folder"] = folder_states
        account.write({"outlook_delta_tokens": tokens})

        changes = bool(
            added_by_folder
            or flags_changed
            or deleted_by_folder
            or moved_by_folder
            or refresh_folders
        )

        if added_by_folder:
            self._touch_folders_last_sync_at(account, set(added_by_folder.keys()))

        self._emit_notifications(
            account,
            added_by_folder,
            flags_changed,
            deleted_by_folder,
            moved_by_folder,
            refresh_folders,
        )

        return {
            "ok": True,
            "changes": changes,
            "deleted": sum(len(v) for v in deleted_by_folder.values()),
            "truncated": bool(truncated),
            "new_count": sum(
                len(v.get("index_ids", [])) for v in added_by_folder.values()
            ),
        }

    # ------------------------------------------------------------------
    # Delta collection
    # ------------------------------------------------------------------

    def _collect_folder_delta(
        self,
        *,
        account,
        sess,
        cursor: str,
        owner: str,
        folder_name: str,
        initialized: bool,
        added_by_folder: Dict[str, Dict[str, List]],
        flags_changed: Dict[str, Dict[Tuple[bool, bool], Dict[str, List]]],
        moved_by_folder: Dict[Tuple[str, str], List[str]],
        refresh_folders: Set[str],
        processed_already: int,
        pages_left: int,
    ) -> OutlookFolderDeltaResult:
        removed_ids: List[str] = []
        truncated = False
        processed_start = processed_already

        next_url = cursor
        delta_link: Optional[str] = None
        pages_used = 0

        while next_url:
            if pages_left > 0 and pages_used >= pages_left:
                truncated = True
                break

            resp = self._delta_request(sess, next_url)
            delta_link = resp.get("@odata.deltaLink") or delta_link
            next_url = resp.get("@odata.nextLink")
            pages_used += 1

            items = resp.get("value", []) or []
            stop_after_page = False
            for item in items:
                mid = item.get("id")
                if not mid:
                    continue

                if (
                    self.max_items_per_run > 0
                    and processed_already >= self.max_items_per_run
                ):
                    truncated = True
                    stop_after_page = True
                    break

                processed_already += 1

                if item.get("@removed") is not None:
                    removed_ids.append(str(mid))
                    continue

                self._process_message_item(
                    account=account,
                    item=item,
                    folder_name=folder_name,
                    is_initialized=initialized,
                    added_by_folder=added_by_folder,
                    flags_changed=flags_changed,
                    moved_by_folder=moved_by_folder,
                    refresh_folders=refresh_folders,
                )

            if stop_after_page:
                break

            if not next_url:
                break

            self._renew_lease(account_id=account.id, owner=owner)

        folder_initialized = initialized or bool(delta_link)
        cursor_out = (next_url or delta_link or cursor).strip()
        return OutlookFolderDeltaResult(
            cursor=cursor_out,
            initialized=folder_initialized,
            removed_ids=removed_ids,
            processed_items=(processed_already - processed_start),
            pages_used=pages_used,
            truncated=truncated,
        )

    def _delta_request(self, sess, url: str) -> dict:
        r = sess.get(url, timeout=30)
        if r.status_code == 410:
            raise DeltaExpiredError()
        if r.status_code == 400:
            _logger.error("[Outlook Delta] 400 from Graph url=%s body=%s", url, r.text)
        r.raise_for_status()
        return r.json() or {}

    # ------------------------------------------------------------------
    # SSOT write + enqueue
    # ------------------------------------------------------------------

    def _process_message_item(
        self,
        *,
        account,
        item: dict,
        folder_name: str,
        is_initialized: bool,
        added_by_folder: Dict[str, Dict[str, List]],
        flags_changed: Dict[str, Dict[Tuple[bool, bool], Dict[str, List]]],
        moved_by_folder: Dict[Tuple[str, str], List[str]],
        refresh_folders: Set[str],
    ) -> None:
        msg = self._message_from_delta(item, account.id, folder_name)
        if not msg:
            return

        Index = self.env["maildesk.message_index"].sudo()

        provider_data = self._index_vals(account, folder_name, msg)

        # Outbound reconciliation (primary): outgoing_id (X-MailDesk-Outgoing-ID)
        if msg.outgoing_id:
            pending = Index.search(
                [
                    ("account_id", "=", account.id),
                    ("provider", "=", "outlook"),
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
                provider="outlook",
                provider_uid=str(msg.id),
                provider_folder=folder_name,
                provider_message_data=provider_data,
            ):
                if old_folder and old_folder != folder_name:
                    moved_by_folder.setdefault((old_folder, folder_name), []).append(
                        str(old_uid or msg.id)
                    )
                else:
                    refresh_folders.add(str(folder_name))

                if len(pending) == 1:
                    enqueue = EnqueueIngestForMessageIndex(IngestQueueAdapter(self.env))
                    try:
                        enqueue.execute(
                            EnqueueIngestForMessageIndexParams(
                                index_id=pending[0].id, priority=10
                            )
                        )
                    except Exception:
                        _logger.debug(
                            "Failed to enqueue ingest for confirmed outlook outgoing %s",
                            msg.id,
                            exc_info=True,
                        )
                return

            touched = Index.touch_existing_outgoing_delivery(
                account_id=account.id,
                provider="outlook",
                provider_folder=folder_name,
                outgoing_id=msg.outgoing_id,
                provider_message_data=provider_data,
            )
            if touched:
                return

        # Fallback: Message-ID confirmation for local_pending (strict guards inside model method).
        if (not msg.outgoing_id) and msg.message_header_id:
            if Index.confirm_outbound_delivery_by_message_id(
                account_id=account.id,
                provider="outlook",
                provider_uid=str(msg.id),
                provider_folder=folder_name,
                message_id=msg.message_header_id,
                message_from=msg.email_from,
                provider_message_data=provider_data,
            ):
                refresh_folders.add(str(folder_name))
                confirmed = Index.search(
                    [
                        ("account_id", "=", account.id),
                        ("provider", "=", "outlook"),
                        ("folder", "=", folder_name),
                        ("uid", "=", str(msg.id)),
                    ],
                    limit=1,
                )
                if confirmed:
                    confirmed.write({"ingest_allowed": True})
                    enqueue = EnqueueIngestForMessageIndex(IngestQueueAdapter(self.env))
                    try:
                        enqueue.execute(
                            EnqueueIngestForMessageIndexParams(
                                index_id=confirmed.id, priority=10
                            )
                        )
                    except Exception:
                        _logger.debug(
                            "Failed to enqueue ingest for confirmed outlook (Message-ID fallback) %s",
                            msg.id,
                            exc_info=True,
                        )
                return

        existing = Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "outlook"),
                ("uid", "=", str(msg.id)),
            ],
            limit=2,
        )

        if existing:
            rec = existing[0]
            old_folder = rec.folder
            old_is_read = rec.is_read
            old_is_starred = rec.is_starred

            vals = self._index_vals(account, folder_name, msg)
            if old_folder != folder_name:
                vals["folder"] = folder_name
                rec.write(vals)
                moved_by_folder.setdefault((old_folder, folder_name), []).append(
                    str(msg.id)
                )
                # Clean up duplicates in destination if any (non-local_pending)
                dupes = Index.search(
                    [
                        ("account_id", "=", account.id),
                        ("provider", "=", "outlook"),
                        ("folder", "=", folder_name),
                        ("uid", "=", str(msg.id)),
                        ("id", "!=", rec.id),
                        ("local_pending", "=", False),
                    ]
                )
                if dupes:
                    dupes.unlink()
            else:
                index_id, inserted = Index.upsert_one_with_inserted(vals)
                if not index_id:
                    return

            if (
                old_is_read is not None
                and old_is_starred is not None
                and (old_is_read != msg.is_read or old_is_starred != msg.is_starred)
            ):
                state_key = (msg.is_read, msg.is_starred)
                flags_changed.setdefault(folder_name, {}).setdefault(
                    state_key, {"uids": [], "index_ids": []}
                )
                flags_changed[folder_name][state_key]["uids"].append(str(msg.id))
                flags_changed[folder_name][state_key]["index_ids"].append(int(rec.id))

            return

        index_id, inserted = Index.upsert_one_with_inserted(
            self._index_vals(account, folder_name, msg)
        )
        if not index_id or not inserted:
            return

        added = added_by_folder.setdefault(
            folder_name, {"uids": [], "index_ids": [], "messages": []}
        )
        added["uids"].append(str(msg.id))
        if is_initialized:
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

        enqueue = EnqueueIngestForMessageIndex(IngestQueueAdapter(self.env))
        try:
            enqueue.execute(EnqueueIngestForMessageIndexParams(index_id=index_id))
        except Exception as e:
            _logger.error(
                "Failed to enqueue ingest for index_id=%s account_id=%s: %s",
                index_id,
                account.id,
                e,
                exc_info=True,
            )

    def _index_vals(self, account, folder_name: str, msg: Message) -> dict:
        flags = self._flags_from_state(msg.is_read, msg.is_starred)
        return {
            "account_id": account.id,
            "provider": "outlook",
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
                ("provider", "=", "outlook"),
                ("uid", "in", ids),
                ("local_pending", "=", False),
            ]
        )
        deleted_by_folder: Dict[str, List[str]] = {}
        for rec in recs:
            deleted_by_folder.setdefault(rec.folder, []).append(rec.uid)
        if recs:
            # This path can run concurrently (cron vs UI-triggered realtime sync).
            # A serialization failure must not abort the whole sync transaction.
            domain = [
                ("account_id", "=", account.id),
                ("provider", "=", "outlook"),
                ("uid", "in", ids),
                ("local_pending", "=", False),
            ]
            for attempt in range(1, 4):
                try:
                    with self.env.cr.savepoint():
                        recs = Index.search(domain)
                        if recs:
                            recs.unlink()
                    break
                except psycopg2.errors.SerializationFailure:
                    _logger.info(
                        "[Outlook Delta] Serialization failure while deleting message_index rows "
                        "(account=%s attempt=%s ids=%s); retrying.",
                        account.id,
                        attempt,
                        ids,
                    )
                    continue
            else:
                _logger.warning(
                    "[Outlook Delta] Failed to delete message_index rows after retries "
                    "(account=%s ids=%s).",
                    account.id,
                    ids,
                )
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
        moved_by_folder: Dict[Tuple[str, str], List[str]],
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
                origin="outlook_incremental",
                index_ids=data.get("index_ids") or [],
                messages=data.get("messages") or [],
            )
            affected_folders.add(folder_name)
            refreshed_by_list_events.add(folder_name)

        for (source_folder, dest_folder), uids in moved_by_folder.items():
            if not uids:
                continue
            self.notifier.notify_messages_moved(
                account_id=account.id,
                source_folder=source_folder,
                destination_folder=dest_folder,
                uids=uids,
            )
            affected_folders.add(source_folder)
            affected_folders.add(dest_folder)
            refreshed_by_list_events.add(source_folder)
            refreshed_by_list_events.add(dest_folder)

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
                ("provider", "=", "outlook"),
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

    def _build_folder_map(self, account) -> Dict[str, str]:
        Folder = self.env["mailbox.folder"].sudo()
        folders = Folder.search([("account_id", "=", account.id)])
        mapping: Dict[str, str] = {}
        for f in folders:
            if getattr(f, "outlook_graph_id", None):
                mapping[str(f.outlook_graph_id)] = f.imap_name or f.name
        return mapping

    def _message_from_delta(
        self, item: dict, account_id: int, folder_name: str
    ) -> Optional[Message]:
        if not item or not item.get("id"):
            return None

        in_reply_to = ""
        references = ""

        sender_obj = (item.get("sender") or item.get("from") or {}).get(
            "emailAddress", {}
        ) or {}
        sender = sender_obj.get("address", "") or ""
        sender_name = sender_obj.get("name", "") or ""
        email_from = sender.lower()

        dt_raw = item.get("receivedDateTime") or item.get("sentDateTime")
        msg_dt = self._parse_graph_datetime(dt_raw)

        to_disp = ", ".join(
            [
                (x.get("emailAddress") or {}).get("address", "")
                for x in (item.get("toRecipients") or [])
            ]
        )
        cc_disp = ", ".join(
            [
                (x.get("emailAddress") or {}).get("address", "")
                for x in (item.get("ccRecipients") or [])
            ]
        )

        preview = (item.get("bodyPreview") or "").strip()
        if preview:
            preview = preview.replace("\r", " ").replace("\n", " ")
            if len(preview) > 160:
                preview = preview[:160]

        flag = (item.get("flag") or {}).get("flagStatus")
        is_starred = flag == "flagged"
        is_read = bool(item.get("isRead"))
        has_atts = bool(item.get("hasAttachments"))

        msg_id_norm = msgid_header(item.get("internetMessageId") or "")
        thread_id = item.get("conversationId") or ""

        return Message(
            id=item.get("id"),
            thread_id=thread_id,
            account_id=account_id,
            message_header_id=msg_id_norm,
            in_reply_to=in_reply_to,
            references=references,
            date=msg_dt,
            subject=item.get("subject") or "(no subject)",
            email_from=email_from,
            sender_display_name=sender_name,
            to_display=to_disp,
            cc_display=cc_disp,
            bcc_display="",
            snippet=preview,
            folder_ids=[folder_name],
            is_read=is_read,
            is_starred=is_starred,
            has_attachments=has_atts,
            metadata={},
        )

    def _parse_graph_datetime(self, dt_raw: Optional[str]) -> datetime:
        if not dt_raw:
            return datetime(1970, 1, 1)
        try:
            if dt_raw.endswith("Z"):
                dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(dt_raw)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            return datetime(1970, 1, 1)

    def _flags_from_state(self, is_read: bool, is_starred: bool) -> str:
        flags = []
        if is_read:
            flags.append("\\Seen")
        if is_starred:
            flags.append("\\Flagged")
        return " ".join(flags)

    # ------------------------------------------------------------------
    # Delta expiration recovery
    # ------------------------------------------------------------------

    def _handle_delta_expired(self, account) -> dict:
        account.write(
            {
                "outlook_delta_link": False,
                "outlook_delta_tokens": {},
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
            if "outlook_backfill_next_link" in folder._fields:
                vals["outlook_backfill_next_link"] = False
            folder.write(vals)

        if self.notifier:
            self.notifier.notify_full_refresh(account_id=account.id, folder=None)

        return {"ok": True, "mode": "delta_expired", "changes": True}

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    def _record_error(self, account, exc: Exception):
        msg = str(exc)
        backoff_at = fields.Datetime.now() + relativedelta(minutes=10)
        # Never allow error reporting to fail the current transaction.
        try:
            with self.env.cr.savepoint():
                account.write({"backoff_until": backoff_at})
        except psycopg2.Error:
            _logger.warning(
                "Failed to write backoff_until after Outlook sync error for account %s",
                account.id,
            )
        _logger.warning("Outlook sync error for account %s: %s", account.id, msg)

    def _renew_lease(self, account_id: int, owner: str):
        try:
            self.env["maildesk.account_lease"].sudo().renew(
                account_id, ttl_seconds=self.lease_ttl_seconds, owner=owner
            )
        except Exception:
            return

    # ------------------------------------------------------------------
    # Folder-scoped delta helpers
    # ------------------------------------------------------------------

    def _get_delta_tokens(self, account) -> dict:
        tokens = account.outlook_delta_tokens or {}
        return tokens if isinstance(tokens, dict) else {}

    def _folders_for_delta(self, folder_map: Dict[str, str]) -> List[Tuple[str, str]]:
        items = [(str(gid), folder_map[gid]) for gid in folder_map.keys()]
        return sorted(items, key=lambda x: (x[1] or "", x[0] or ""))

    def _initial_delta_url(self, base_url: str, folder_graph_id: str) -> str:
        # State-only delta payload (no bodies, no full headers).
        select = (
            "id,subject,sender,receivedDateTime,sentDateTime,hasAttachments,isRead,"
            "ccRecipients,toRecipients,conversationId,flag,internetMessageId,bodyPreview"
        )
        return (
            f"{base_url}/me/mailFolders/{folder_graph_id}/messages/delta"
            f"?$select={select}&$top=50"
        )

    def _resolve_removed_candidates(
        self,
        *,
        account,
        sess,
        base_url: str,
        folder_map: Dict[str, str],
        removed_candidates: List[Tuple[str, str]],
        deleted_by_folder: Dict[str, List[str]],
        moved_by_folder: Dict[Tuple[str, str], List[str]],
    ) -> None:
        """
        Graph message delta reports `@removed.reason=deleted` when a message is deleted OR moved
        out of the folder. Resolve deterministically via `GET /me/messages/{id}?$select=parentFolderId`.
        """
        Index = self.env["maildesk.message_index"].sudo()

        for source_folder, mid in removed_candidates:
            parent_id = self._get_message_parent_folder_id(sess, base_url, mid)
            if not parent_id:
                deleted = self._delete_messages(account, [mid])
                for folder_name, uids in deleted.items():
                    deleted_by_folder.setdefault(folder_name, []).extend(uids)
                continue

            dest_folder = folder_map.get(str(parent_id) or "", "")
            if not dest_folder:
                deleted = self._delete_messages(account, [mid])
                for folder_name, uids in deleted.items():
                    deleted_by_folder.setdefault(folder_name, []).extend(uids)
                continue

            rec = Index.search(
                [
                    ("account_id", "=", account.id),
                    ("provider", "=", "outlook"),
                    ("uid", "=", str(mid)),
                ],
                limit=1,
            )
            if not rec:
                continue

            if rec.folder != dest_folder:
                old_folder = rec.folder
                rec.write({"folder": dest_folder})
                moved_by_folder.setdefault((old_folder, dest_folder), []).append(
                    str(mid)
                )

    def _get_message_parent_folder_id(
        self, sess, base_url: str, message_id: str
    ) -> Optional[str]:
        url = f"{base_url}/me/messages/{message_id}?$select=parentFolderId"
        r = sess.get(url, timeout=15)
        if r.status_code == 404:
            return None
        if r.status_code == 410:
            raise DeltaExpiredError()
        r.raise_for_status()
        data = r.json() or {}
        parent = data.get("parentFolderId")
        return str(parent) if parent else None
