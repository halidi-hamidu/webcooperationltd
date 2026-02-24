# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Open Thread Messages.

Implements the application-level use case for Open Thread Messages.
Layer: application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenThreadMessagesParams:
    account_id: int
    thread_id: str
    include_bodies: bool = True


class OpenThreadMessagesDeps(Protocol):
    # Models / access
    def account_browse(self, account_id: int) -> Any: ...
    def check_account_access(self, account: Any) -> None: ...

    # SSOT thread topology
    def get_thread_index_records(self, account: Any, thread_id: str) -> List[Any]: ...
    def folders_by_name(
        self, account_id: int, folder_names: List[str]
    ) -> Dict[str, Any]: ...

    # UI cache
    def cache_fetch_body_map(
        self, index_ids: List[int]
    ) -> Dict[int, Dict[str, Any]]: ...
    def cache_resolve_canonical_index_id(self, index_id: int) -> int: ...

    # DTO builder (must mirror OpenMessage DTO shape)
    def build_open_message_dto_from_cache(
        self, *, index_rec: Any, cached: Dict[str, Any], account: Any, folder: Any
    ) -> Dict[str, Any]: ...

    # Provider fetch for cache miss
    def hydrate_message(self, index_rec: Any, folder: Any) -> Dict[str, Any]: ...


class OpenThreadMessages:
    """
    Fetch all messages in a thread, with bodies, in a SINGLE use-case execution.

    Contract:
    - Thread topology always comes from SSOT (maildesk.message_index.thread_id).
    - Bodies/attachments are read from maildesk.ui_cache first.
    - If cache miss, fetches from provider via OpenMessage and writes to cache.
    """

    def __init__(self, deps: OpenThreadMessagesDeps):
        self._deps = deps

    def execute(self, params: OpenThreadMessagesParams) -> List[Dict[str, Any]]:
        if not params.thread_id:
            return []

        account = self._deps.account_browse(int(params.account_id))
        if not account:
            return []

        self._deps.check_account_access(account)

        index_recs = self._deps.get_thread_index_records(account, params.thread_id)
        if not index_recs:
            return []

        folder_names = sorted({r.folder for r in index_recs if r.folder})
        folders = self._deps.folders_by_name(int(account.id), folder_names)

        canonical_by_index: Dict[int, int] = {}
        canonical_ids_set = set()
        for rec in index_recs:
            canon = self._deps.cache_resolve_canonical_index_id(int(rec.id))
            canonical_by_index[int(rec.id)] = int(canon)
            canonical_ids_set.add(int(canon))

        canonical_ids = sorted(canonical_ids_set)
        cache_map = self._deps.cache_fetch_body_map(canonical_ids)

        out: List[Dict[str, Any]] = []
        for rec in index_recs:
            folder = folders.get(getattr(rec, "folder", None)) if folders else None
            canon_id = canonical_by_index.get(int(rec.id), int(rec.id))
            cached = cache_map.get(int(canon_id))

            if cached and cached.get("body_html"):
                # Cache hit - use cached body
                dto = self._deps.build_open_message_dto_from_cache(
                    index_rec=rec,
                    cached=cached,
                    account=account,
                    folder=folder,
                )
            else:
                # Cache miss - fetch from provider
                _logger.debug(
                    "[OpenThreadMessages] Cache miss for index_id=%d, fetching from provider",
                    rec.id,
                )
                try:
                    dto = self._deps.hydrate_message(rec, folder)
                except Exception as e:
                    _logger.warning(
                        "[OpenThreadMessages] Failed to hydrate index_id=%d: %s",
                        rec.id,
                        e,
                    )
                    # Re-check cache - another request may have populated it
                    refreshed_cache = self._deps.cache_fetch_body_map([int(canon_id)])
                    refreshed = refreshed_cache.get(int(canon_id))
                    if refreshed and refreshed.get("body_html"):
                        dto = self._deps.build_open_message_dto_from_cache(
                            index_rec=rec,
                            cached=refreshed,
                            account=account,
                            folder=folder,
                        )
                    else:
                        # Still no cache - return minimal DTO
                        dto = self._deps.build_open_message_dto_from_cache(
                            index_rec=rec,
                            cached={
                                "body_html": "",
                                "body_text": "",
                                "attachments": [],
                            },
                            account=account,
                            folder=folder,
                        )
            out.append(dto)

        out.sort(key=lambda m: m.get("sort_ts", 0) or 0)
        return out
