# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)

"""
UpdateTagsUnified Use-Case: Handles tag updates for all message types.

Handles:
- Drafts (maildesk.draft)
- Message index entries (maildesk.message_index)

Layer: application
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Protocol

_logger = logging.getLogger(__name__)


class TaggableType(Enum):
    """Type of taggable entity."""

    DRAFT = "draft"
    MESSAGE_INDEX = "message_index"


@dataclass(frozen=True)
class UpdateTagsParams:
    """Parameters for updating tags."""

    message_ids: List[str]
    tag_ids: List[int]


class DraftRepositoryProtocol(Protocol):
    """Protocol for draft repository."""

    def search(self, domain: list, limit: int = None) -> Any: ...


class MessageIndexRepositoryProtocol(Protocol):
    """Protocol for message_index repository."""

    def get_by_id(self, index_id: int) -> Any: ...

    def get_ssot_info(self, index_id: int) -> Optional[dict]: ...


class TagUpdateServiceProtocol(Protocol):
    """Protocol for tag update operations."""

    def update_draft_tags(self, draft_id: int, tag_ids: List[int]) -> dict:
        """Update tags on a draft."""
        ...

    def update_index_tags(
        self, account_id: int, folder: str, uid: str, tag_ids: List[int]
    ) -> dict:
        """Update tags on a message_index entry."""
        ...


class SSotNotifierProtocol(Protocol):
    """Protocol for bus notifications."""

    def notify_tags_changed(
        self,
        account_id: int,
        folder: str,
        uids: List[str],
        tag_ids: List[int],
    ) -> None: ...


class UpdateTagsUnified:
    """
    Unified use-case for updating tags on any taggable entity.

    Routes to appropriate update logic based on entity type.
    """

    def __init__(
        self,
        draft_repo: DraftRepositoryProtocol,
        index_repo: MessageIndexRepositoryProtocol,
        tag_service: TagUpdateServiceProtocol,
        notifier: Optional[SSotNotifierProtocol] = None,
    ):
        """
        Initialize use-case.

        Args:
            draft_repo: Draft repository
            index_repo: Message index repository
            tag_service: Tag update service
            notifier: Optional bus notifier
        """
        self._draft_repo = draft_repo
        self._index_repo = index_repo
        self._tag_service = tag_service
        self._notifier = notifier

    def execute(self, params: UpdateTagsParams) -> dict:
        """
        Execute tag updates.

        Args:
            params: UpdateTagsParams

        Returns:
            Dict with update counts
        """
        if not params.message_ids:
            return {"drafts": 0, "messages": 0, "failed": 0}

        results = {"drafts": 0, "messages": 0, "failed": 0}
        changed_by_account_folder = {}

        for msg_id in params.message_ids:
            try:
                msg_id_int = int(msg_id)
                entity_type = self._determine_type(msg_id_int)

                if entity_type == TaggableType.DRAFT:
                    result = self._update_draft_tags(msg_id_int, params.tag_ids)
                    if result:
                        results["drafts"] += 1
                    else:
                        results["failed"] += 1
                else:
                    result = self._update_index_tags(msg_id_int, params.tag_ids)
                    if result:
                        results["messages"] += 1
                        # Track for bus notification
                        key = (result["account_id"], result["folder"])
                        changed_by_account_folder.setdefault(key, []).append(
                            result["uid"]
                        )
                    else:
                        results["failed"] += 1

            except (ValueError, TypeError) as e:
                _logger.warning("[UpdateTagsUnified] Invalid ID %s: %s", msg_id, e)
                results["failed"] += 1

        # Emit bus events for message_index updates
        if self._notifier:
            for (account_id, folder), uids in changed_by_account_folder.items():
                if uids:
                    self._notifier.notify_tags_changed(
                        account_id=account_id,
                        folder=folder,
                        uids=list(dict.fromkeys(uids)),
                        tag_ids=params.tag_ids,
                    )

        _logger.info(
            "[UpdateTagsUnified] Updated: drafts=%d, messages=%d, failed=%d",
            results["drafts"],
            results["messages"],
            results["failed"],
        )

        return results

    def _determine_type(self, msg_id: int) -> TaggableType:
        """Determine entity type by checking repositories."""
        draft = self._draft_repo.search([("id", "=", msg_id)], limit=1)
        if draft:
            return TaggableType.DRAFT
        return TaggableType.MESSAGE_INDEX

    def _update_draft_tags(self, draft_id: int, tag_ids: List[int]) -> Optional[dict]:
        """Update tags on a draft."""
        try:
            return self._tag_service.update_draft_tags(draft_id, tag_ids)
        except Exception as e:
            _logger.error(
                "[UpdateTagsUnified] Failed to update draft %d: %s", draft_id, e
            )
            return None

    def _update_index_tags(self, index_id: int, tag_ids: List[int]) -> Optional[dict]:
        """Update tags on a message_index entry."""
        try:
            info = self._index_repo.get_ssot_info(index_id)
            if not info:
                _logger.warning("[UpdateTagsUnified] Index %d not found", index_id)
                return None

            result = self._tag_service.update_index_tags(
                info["account_id"], info["folder"], str(info["uid"]), tag_ids
            )

            if result:
                return {
                    "account_id": info["account_id"],
                    "folder": info["folder"],
                    "uid": info["uid"],
                    "tags": result,
                }
            return None

        except Exception as e:
            _logger.error(
                "[UpdateTagsUnified] Failed to update index %d: %s", index_id, e
            )
            return None
