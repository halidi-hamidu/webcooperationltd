# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk List Messages SSOT.

Implements the application-level use case for List Messages SSOT.
Layer: application.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple


class ListMessagesSsotDeps(Protocol):
    # Environment / access
    def registry_ready(self) -> bool: ...

    # Folder / account retrieval
    def folder_browse(self, folder_id: int) -> Any: ...
    def folder_exists(self, folder: Any) -> bool: ...
    def folder_account(self, folder: Any) -> Any: ...
    def folder_imap_name(self, folder: Any) -> Optional[str]: ...
    def folder_display_name(self, folder: Any) -> Optional[str]: ...
    def folder_type(self, folder: Any) -> Optional[str]: ...

    # Account selection
    def accounts_for_id(self, account_id: int) -> Sequence[Any]: ...
    def user_accounts(self) -> Sequence[Any]: ...

    # Provider routing
    def is_gmail_account(self, account: Any) -> bool: ...
    def is_outlook_account(self, account: Any) -> bool: ...

    # SSOT index search
    def search_index_records(
        self, account: Any, folder_name: str, provider: str, params: Any
    ) -> Tuple[List[Any], int]: ...
    def has_any_indexed(
        self, account: Any, folder_name: str, provider: Optional[str] = None
    ) -> bool: ...
    def build_records_from_index(
        self, account: Any, folder: Any, index_records: List[Any], partner_cache: Dict
    ) -> List[Dict[str, Any]]: ...

    # Overlays, tags, drafts (legacy-equivalent)
    def apply_state_overlays(
        self,
        account: Any,
        folder_name: Optional[str],
        records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]: ...
    def apply_overrides_and_tags(
        self,
        account: Any,
        folder: Any,
        records: List[Dict[str, Any]],
        total: int,
        tag_ids: Optional[List[int]],
    ) -> Tuple[List[Dict[str, Any]], int]: ...
    def get_tags_for_message_ids(
        self, account_id: int, msg_ids: List[str]
    ) -> Mapping[str, List[int]]: ...
    def append_local_drafts(
        self,
        *,
        account: Any,
        folder: Any,
        records: List[Dict[str, Any]],
        total: int,
        search: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], int]: ...

    # Sorting helper
    def safe_dt(self, rec: Mapping[str, Any]) -> datetime: ...

    # Folder resolution
    def resolve_inbox_folder(self, account: Any) -> Any: ...


@dataclass(frozen=True)
class ListMessagesParams:
    """Parameters for listing messages."""

    account_id: Optional[int] = None
    folder_id: Optional[int] = None
    filter: Optional[str] = None
    search: Optional[str] = None
    offset: int = 0
    limit: int = 30
    partner_id: Optional[int] = None
    email_from: Optional[str] = None
    tag_ids: Optional[List[int]] = None


@dataclass(frozen=True)
class ListMessagesSsotResult:
    records: List[Dict[str, Any]]
    totalMessagesCount: int
    ssot_miss: bool = False


class ListMessagesSsot:
    """
    SSOT list path: read from maildesk.message_index with TTL UI cache.
    """

    def __init__(self, deps: ListMessagesSsotDeps):
        self._deps = deps

    def execute(self, params) -> Dict[str, Any]:
        if not self._deps.registry_ready():
            return ListMessagesSsotResult([], 0, False).__dict__

        partner_cache: Dict[str, Any] = {}

        if params.folder_id:
            res = self._list_folder(params, partner_cache)
            return res.__dict__

        res = self._list_accounts(params, partner_cache)
        return res.__dict__

    def _provider_for(self, account) -> str:
        if self._deps.is_gmail_account(account):
            return "gmail"
        if self._deps.is_outlook_account(account):
            return "outlook"
        return "imap"

    def _folder_name_for(self, folder, provider: str) -> str:
        return (
            self._deps.folder_imap_name(folder)
            or self._deps.folder_display_name(folder)
            or ("ALL_MAIL" if provider in ("gmail", "outlook") else "INBOX")
        )

    def _list_folder(self, params, partner_cache) -> ListMessagesSsotResult:
        folder = self._deps.folder_browse(params.folder_id)
        if not self._deps.folder_exists(folder):
            return ListMessagesSsotResult([], 0, False)

        account = self._deps.folder_account(folder)
        provider = self._provider_for(account)
        folder_name = self._folder_name_for(folder, provider)
        folder_type = (self._deps.folder_type(folder) or "").strip().lower()
        folder_name_norm = (folder_name or "").strip().lower()
        folder_display_name = (
            (self._deps.folder_display_name(folder) or "").strip().lower()
        )

        # Robust check to ensure we identify Drafts even if folder_type is missing/wrong
        # or if the IMAP name is namespaced (e.g. INBOX.Drafts, [Gmail]/Drafts).
        is_drafts_folder = (
            folder_type in {"drafts", "draft"}
            or folder_name_norm in {"drafts", "draft"}
            or folder_display_name in {"drafts", "draft"}
            or folder_name_norm.endswith("/drafts")
            or folder_name_norm.endswith(".drafts")
        )

        # Single-query list fetch via MessageIndexQueryRepo
        # Tags, state, and pending operations already denormalized in message_index
        index_records, total = self._deps.search_index_records(
            account, folder_name, provider, params
        )
        if total == 0 and not self._deps.has_any_indexed(
            account, folder_name, provider
        ):
            # Drafts folder must still show internal drafts (maildesk.draft),
            # even when SSOT has no indexed messages for this folder yet.
            if not is_drafts_folder:
                return ListMessagesSsotResult([], 0, True)

        # Build DTOs - tags already in index_records.tag_ids (no merge needed)
        records = self._deps.build_records_from_index(
            account, folder, index_records, partner_cache
        )

        # NO overlays, NO tag merges, NO Python sorting
        # message_index is complete SSOT with SQL-level sorting

        # Handle drafts folder special case (local drafts not in message_index)
        if is_drafts_folder:
            records, total = self._deps.append_local_drafts(
                account=account,
                folder=folder,
                records=records,
                total=total,
                search=params.search,
            )
            # Re-sort after appending drafts
            records.sort(
                key=lambda r: (
                    r.get("sort_ts")
                    or int(r.get("date").timestamp() if r.get("date") else 0),
                    str(r.get("uid") or ""),
                ),
                reverse=True,
            )

        return ListMessagesSsotResult(records, total, False)

    def _list_accounts(self, params, partner_cache) -> ListMessagesSsotResult:
        accounts = (
            self._deps.accounts_for_id(params.account_id)
            if params.account_id
            else self._deps.user_accounts()
        )
        if not accounts:
            return ListMessagesSsotResult([], 0, False)

        need = params.offset + params.limit
        collected: List[Dict[str, Any]] = []
        total_count_approx = 0
        indexed_accounts = 0
        lookup_params = type(params)(
            account_id=params.account_id,
            folder_id=params.folder_id,
            filter=params.filter,
            search=params.search,
            offset=0,
            limit=need,
            partner_id=params.partner_id,
            email_from=params.email_from,
            tag_ids=params.tag_ids,
        )

        for acc in accounts:
            provider = self._provider_for(acc)

            # Account-level view: aggregate ALL folders, not just INBOX
            # folder_name = None signals repository to query all folders
            folder = None
            folder_name = None  # No folder filter - get all messages for this account

            index_records, total = self._deps.search_index_records(
                acc, folder_name, provider, lookup_params
            )
            if total == 0 and not self._deps.has_any_indexed(
                acc, folder_name, provider
            ):
                continue

            indexed_accounts += 1
            records = self._deps.build_records_from_index(
                acc, folder, index_records, partner_cache
            )

            collected.extend(records)
            total_count_approx += total

            if len(collected) >= need:
                continue

        if indexed_accounts == 0:
            return ListMessagesSsotResult([], 0, True)

        collected.sort(
            key=lambda r: (self._deps.safe_dt(r), str(r.get("uid") or 0)),
            reverse=True,
        )
        page = collected[params.offset : params.offset + params.limit]
        return ListMessagesSsotResult(page, total_count_approx, False)
