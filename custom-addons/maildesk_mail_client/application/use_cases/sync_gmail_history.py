# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Sync Gmail History.

Implements the application-level use case for Sync Gmail History.
Layer: application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from dateutil.relativedelta import relativedelta
from googleapiclient.errors import HttpError
from odoo import fields

from ...adapters.gmail_adapter import GmailAdapter
from ...infrastructure.adapters.ingest_queue_adapter import IngestQueueAdapter
from ...domain.contracts import Message
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
    deleted_ids: Set[str]
    labels_removed: Dict[str, Set[str]]


class SyncGmailHistory:
    def __init__(self, env, lease_ttl_seconds: int = 300):
        self.env = env
        self.lease_ttl_seconds = lease_ttl_seconds

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def execute(self, account_id: int) -> dict:
        Account = self.env["mailbox.account"].sudo()
        account = Account.browse(int(account_id))
        if not account.exists() or not account.is_gmail:
            return {"ok": False, "reason": "not_gmail"}

        if account.backoff_until and account.backoff_until > fields.Datetime.now():
            return {"ok": False, "reason": "backoff"}

        Lease = self.env["maildesk.account_lease"].sudo()
        owner = f"gmail-sync:{self.env.cr.dbname}:{account.id}"
        if not Lease.try_acquire(
            account.id, ttl_seconds=self.lease_ttl_seconds, owner=owner
        ):
            return {"ok": False, "reason": "lease_locked"}

        try:
            return self._sync_account(account, owner)
        finally:
            Lease.release(account.id, owner=owner)

    # ---------------------------------------------------------------------
    # Core flow
    # ---------------------------------------------------------------------

    def _sync_account(self, account, owner: str) -> dict:
        service = self._get_service(account)

        if not account.gmail_last_history_id or account.gmail_last_history_id == "0":
            try:
                return self._rebuild(account, service, reason="bootstrap", owner=owner)
            except Exception as e:
                self._record_error(account, e)
                return {"ok": False, "error": str(e)}

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
            try:
                return self._rebuild(
                    account, service, reason="history_expired", owner=owner
                )
            except Exception as e:
                self._record_error(account, e)
                return {"ok": False, "error": str(e)}
        except Exception as e:
            self._record_error(account, e)
            return {"ok": False, "error": str(e)}

    def _incremental(self, account, service, owner: str) -> dict:
        start_id = str(account.gmail_last_history_id)
        hist = self._collect_history(service, start_id, owner, account.id)

        label_id_map = self._get_label_id_map(service)
        folder_map = self._build_folder_map(account)

        messages_to_fetch = set(hist.messages_to_fetch) - set(hist.deleted_ids)
        messages = self._fetch_messages(service, account, sorted(messages_to_fetch))
        current_labels = self._current_label_names(messages, label_id_map)

        if messages:
            self._upsert_messages(
                account,
                messages,
                label_id_map=label_id_map,
                folder_map=folder_map,
                add_all_mail=True,
            )

        if hist.labels_removed:
            self._apply_label_removals(
                account,
                hist.labels_removed,
                label_id_map=label_id_map,
                folder_map=folder_map,
                current_labels=current_labels,
            )

        if hist.deleted_ids:
            self._delete_messages(account, hist.deleted_ids)

        account.write({"gmail_last_history_id": hist.history_id})
        return {
            "ok": True,
            "changes": bool(
                messages_to_fetch or hist.deleted_ids or hist.labels_removed
            ),
            "history_id": hist.history_id,
            "fetched": len(messages_to_fetch),
            "deleted": len(hist.deleted_ids),
        }

    def _rebuild(self, account, service, reason: str, owner: str) -> dict:
        base_history_id = self._get_profile_history_id(service)
        label_id_map = self._get_label_id_map(service)
        folder_map = self._build_folder_map(account)
        Index = self.env["maildesk.message_index"].sudo()

        with self.env.cr.savepoint():
            Index.search(
                [("account_id", "=", account.id), ("provider", "=", "gmail")]
            ).unlink()

            for label_id, label_name in label_id_map.items():
                folder_name = self._folder_name_for_label(label_name, folder_map)
                if not folder_name:
                    continue
                msg_ids = self._list_message_ids_by_label(service, label_id)
                for chunk in self._chunks(msg_ids, 100):
                    messages = self._fetch_messages(service, account, chunk)
                    if not messages:
                        continue
                    self._upsert_messages(
                        account,
                        messages,
                        label_id_map=label_id_map,
                        folder_map=folder_map,
                        add_all_mail=False,
                        forced_folder=folder_name,
                        enqueue_ingest=False,
                        ingest_allowed=False,
                    )
                    self._renew_lease(account_id=account.id, owner=owner)

            all_mail_ids = self._list_message_ids_all_mail(service)
            for chunk in self._chunks(all_mail_ids, 100):
                messages = self._fetch_messages(service, account, chunk)
                if not messages:
                    continue
                self._upsert_messages(
                    account,
                    messages,
                    label_id_map=label_id_map,
                    folder_map=folder_map,
                    add_all_mail=True,
                    force_all_mail_only=True,
                    enqueue_ingest=False,
                    ingest_allowed=False,
                )
                self._renew_lease(account_id=account.id, owner=owner)

            account.write(
                {
                    "gmail_last_history_id": base_history_id,
                    "gmail_last_sync_at": fields.Datetime.now(),
                    "gmail_last_error": False,
                    "backoff_until": False,
                }
            )
        return {"ok": True, "changes": True, "mode": reason}

    # ---------------------------------------------------------------------
    # Gmail API helpers
    # ---------------------------------------------------------------------

    def _get_service(self, account):
        return gmail_build_service(account)

    def _collect_history(
        self, service, start_id: str, owner: str, account_id: int
    ) -> GmailHistoryResult:
        messages_to_fetch: Set[str] = set()
        deleted_ids: Set[str] = set()
        labels_removed: Dict[str, Set[str]] = {}
        history_id = start_id

        page_token = None
        while True:
            resp = self._history_list(service, start_id, page_token)
            history_id = resp.get("historyId") or history_id

            for item in resp.get("history", []) or []:
                for h in item.get("messagesAdded", []) or []:
                    mid = (h.get("message") or {}).get("id")
                    if mid:
                        messages_to_fetch.add(str(mid))
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

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

            self._renew_lease(account_id=account_id, owner=owner)

        return GmailHistoryResult(
            history_id=str(history_id),
            messages_to_fetch=messages_to_fetch,
            deleted_ids=deleted_ids,
            labels_removed=labels_removed,
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

    def _get_label_id_map(self, service) -> Dict[str, str]:
        resp = service.users().labels().list(userId="me").execute()
        labels = resp.get("labels") or []
        return {
            str(label["id"]): str(label["name"]) for label in labels if label.get("id")
        }

    def _list_message_ids_by_label(self, service, label_id: str) -> List[str]:
        msg_ids: List[str] = []
        page_token = None
        while True:
            resp = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=[label_id],
                    maxResults=500,
                    pageToken=page_token,
                )
                .execute()
            )
            msg_ids.extend([m["id"] for m in resp.get("messages", []) or []])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return msg_ids

    def _list_message_ids_all_mail(self, service) -> List[str]:
        msg_ids: List[str] = []
        page_token = None
        while True:
            resp = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q="-in:trash -in:spam",
                    maxResults=500,
                    pageToken=page_token,
                )
                .execute()
            )
            msg_ids.extend([m["id"] for m in resp.get("messages", []) or []])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return msg_ids

    def _get_profile_history_id(self, service) -> str:
        profile = service.users().getProfile(userId="me").execute()
        return str(profile.get("historyId") or "0")

    # ---------------------------------------------------------------------
    # SSOT write helpers
    # ---------------------------------------------------------------------

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
        forced_folder: Optional[str] = None,
        force_all_mail_only: bool = False,
        enqueue_ingest: bool = True,
        ingest_allowed: bool = True,
    ):
        Index = self.env["maildesk.message_index"].sudo()
        enqueue = (
            EnqueueIngestForMessageIndex(IngestQueueAdapter(self.env))
            if enqueue_ingest
            else None
        )

        for msg in messages:
            label_ids = msg.metadata.get("label_ids") or []
            label_names = {
                label_id_map.get(str(lid))
                for lid in label_ids
                if str(lid) in label_id_map
            }
            label_names = {ln for ln in label_names if ln}

            folder_names: Set[str] = set()
            if forced_folder:
                folder_names.add(forced_folder)
            elif not force_all_mail_only:
                for name in label_names:
                    f = self._folder_name_for_label(name, folder_map)
                    if f:
                        folder_names.add(f)

            if add_all_mail and self._is_spam_or_trash(label_names):
                Index.search(
                    [
                        ("account_id", "=", account.id),
                        ("provider", "=", "gmail"),
                        ("folder", "=", "ALL_MAIL"),
                        ("uid", "=", str(msg.id)),
                    ]
                ).unlink()

            include_all_mail = add_all_mail and not self._is_spam_or_trash(label_names)
            if force_all_mail_only:
                folder_names = set()
            if include_all_mail or force_all_mail_only:
                folder_names.add("ALL_MAIL")

            if not folder_names:
                continue

            for folder_name in folder_names:
                flags = self._flags_from_state(msg.is_read, msg.is_starred)
                index_id = Index.upsert_one(
                    {
                        "account_id": account.id,
                        "provider": "gmail",
                        "folder": folder_name,
                        "uid": str(msg.id),
                        "ingest_allowed": bool(ingest_allowed),
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
                if index_id:
                    if enqueue:
                        try:
                            enqueue.execute(
                                EnqueueIngestForMessageIndexParams(index_id=index_id)
                            )
                        except Exception as e:
                            # P0-2: Make enqueue failures visible
                            _logger.error(
                                "Failed to enqueue ingest for index_id=%s account_id=%s: %s",
                                index_id,
                                account.id,
                                e,
                                exc_info=True,
                            )

    def _apply_label_removals(
        self,
        account,
        labels_removed: Dict[str, Set[str]],
        *,
        label_id_map: Dict[str, str],
        folder_map: Dict[str, str],
        current_labels: Dict[str, Set[str]],
    ):
        Index = self.env["maildesk.message_index"].sudo()

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
                Index.search(
                    [
                        ("account_id", "=", account.id),
                        ("provider", "=", "gmail"),
                        ("folder", "=", folder_name),
                        ("uid", "=", str(mid)),
                    ]
                ).unlink()

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

    def _delete_messages(self, account, message_ids: Iterable[str]):
        ids = [str(x) for x in message_ids if x]
        if not ids:
            return
        self.env.cr.execute(
            """
            DELETE FROM maildesk_message_index
            WHERE account_id = %s AND provider = 'gmail' AND uid = ANY(%s)
            """,
            (account.id, ids),
        )

    # ---------------------------------------------------------------------
    # Mapping & misc helpers
    # ---------------------------------------------------------------------

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

    def _chunks(self, items: List[str], size: int) -> Iterable[List[str]]:
        for i in range(0, len(items), size):
            yield items[i : i + size]

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
