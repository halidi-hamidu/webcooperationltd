# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)

"""
DeleteMessagesUnified Use-Case: Handles deletion of all message types.

Handles:
- Drafts (maildesk.draft) → direct delete
- Local sent messages (uid starts with 'local-') → direct delete from message_index
- Regular provider messages → delete via email_state overlay

Layer: application
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Protocol

_logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Type of message for deletion routing."""

    DRAFT = "draft"
    LOCAL_INDEX = "local_index"
    PROVIDER = "provider"


@dataclass(frozen=True)
class DeleteMessagesParams:
    """Parameters for deleting messages."""

    message_ids: List[str]
    folder_id: Optional[int] = None


class DraftRepositoryProtocol(Protocol):
    """Protocol for draft repository."""

    def browse(self, draft_id: int) -> Any: ...

    def exists(self, draft: Any) -> bool: ...

    def delete(self, draft: Any) -> None: ...

    def search(self, domain: list, limit: int = None) -> Any: ...


class MessageIndexRepositoryProtocol(Protocol):
    """Protocol for message_index repository."""

    def get_by_id(self, index_id: int) -> Any: ...

    def is_local_entry(self, record: Any) -> bool: ...

    def delete_by_ids(self, index_ids: List[int]) -> int: ...


class AccessControlProtocol(Protocol):
    """Protocol for access control."""

    def check_account_access(self, account: Any) -> None: ...


class ProviderDeleteProtocol(Protocol):
    """Protocol for provider message deletion."""

    def delete_provider_messages(
        self, message_ids: List[str], folder_id: Optional[int]
    ) -> bool: ...


class DeleteMessagesUnified:
    """
    Unified use-case for deleting messages of any type.

    Routes to appropriate deletion strategy based on message type.
    """

    def __init__(
        self,
        draft_repo: DraftRepositoryProtocol,
        index_repo: MessageIndexRepositoryProtocol,
        access_control: AccessControlProtocol,
        provider_delete: Optional[ProviderDeleteProtocol] = None,
    ):
        """
        Initialize use-case with repositories.

        Args:
            draft_repo: Draft repository
            index_repo: Message index repository
            access_control: Access control service
            provider_delete: Provider message deletion handler (optional)
        """
        self._draft_repo = draft_repo
        self._index_repo = index_repo
        self._access_control = access_control
        self._provider_delete = provider_delete

    def execute(self, params: DeleteMessagesParams) -> dict:
        """
        Execute message deletion.

        Args:
            params: DeleteMessagesParams

        Returns:
            Dict with deleted counts by type
        """
        if not params.message_ids:
            return {"drafts": 0, "local": 0, "provider": 0}

        # Classify messages by type
        classified = self._classify_messages(params.message_ids)

        results = {
            "drafts": 0,
            "local": 0,
            "provider": 0,
        }

        # Delete drafts
        results["drafts"] = self._delete_drafts(classified[MessageType.DRAFT])

        # Delete local message_index entries
        results["local"] = self._delete_local_entries(
            classified[MessageType.LOCAL_INDEX]
        )

        # Delete provider messages
        if self._provider_delete and classified[MessageType.PROVIDER]:
            self._provider_delete.delete_provider_messages(
                classified[MessageType.PROVIDER], params.folder_id
            )
            results["provider"] = len(classified[MessageType.PROVIDER])

        _logger.info(
            "[DeleteMessagesUnified] Deleted: drafts=%d, local=%d, provider=%d",
            results["drafts"],
            results["local"],
            results["provider"],
        )

        return results

    def _classify_messages(self, message_ids: List[str]) -> dict:
        """
        Classify messages by type.

        Args:
            message_ids: List of message IDs

        Returns:
            Dict mapping MessageType to list of IDs
        """
        classified = {
            MessageType.DRAFT: [],
            MessageType.LOCAL_INDEX: [],
            MessageType.PROVIDER: [],
        }

        for msg_id in message_ids:
            try:
                msg_id_int = int(msg_id)
                msg_type = self._determine_type(msg_id_int)
                classified[msg_type].append(msg_id)
            except (ValueError, TypeError):
                # Invalid ID, treat as provider message
                classified[MessageType.PROVIDER].append(msg_id)

        return classified

    def _determine_type(self, msg_id: int) -> MessageType:
        """
        Determine message type by checking repositories.

        Args:
            msg_id: Message ID

        Returns:
            MessageType enum
        """
        # Check if draft
        draft = self._draft_repo.search([("id", "=", msg_id)], limit=1)
        if draft:
            return MessageType.DRAFT

        # Check if local message_index
        index = self._index_repo.get_by_id(msg_id)
        if index and self._index_repo.is_local_entry(index):
            return MessageType.LOCAL_INDEX

        # Default to provider message
        return MessageType.PROVIDER

    def _delete_drafts(self, draft_ids: List[str]) -> int:
        """
        Delete drafts.

        Args:
            draft_ids: List of draft IDs

        Returns:
            Number of deleted drafts
        """
        deleted = 0
        for draft_id in draft_ids:
            try:
                draft = self._draft_repo.browse(int(draft_id))
                if self._draft_repo.exists(draft):
                    self._access_control.check_account_access(draft.account_id)
                    self._draft_repo.delete(draft)
                    deleted += 1
            except Exception as e:
                _logger.warning(
                    "[DeleteMessagesUnified] Failed to delete draft %s: %s", draft_id, e
                )

        return deleted

    def _delete_local_entries(self, index_ids: List[str]) -> int:
        """
        Delete local message_index entries.

        Args:
            index_ids: List of message_index IDs

        Returns:
            Number of deleted entries
        """
        if not index_ids:
            return 0

        try:
            int_ids = [int(i) for i in index_ids]

            # Check access for each entry
            for idx_id in int_ids:
                record = self._index_repo.get_by_id(idx_id)
                if record and hasattr(record, "account_id"):
                    self._access_control.check_account_access(record.account_id)

            return self._index_repo.delete_by_ids(int_ids)
        except Exception as e:
            _logger.warning(
                "[DeleteMessagesUnified] Failed to delete local entries: %s", e
            )
            return 0
