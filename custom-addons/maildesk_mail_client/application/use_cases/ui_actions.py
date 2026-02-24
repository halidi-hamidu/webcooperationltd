# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk UI Actions.

Implements the application-level use case for UI Actions.
Layer: application.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple

from ...domain.contracts.ssot_notification_contract import SSotChangeNotifier

_logger = logging.getLogger(__name__)


class UIActionDeps(Protocol):
    """
    Dependency surface required to run UI action use-cases.

    These use-cases write ONLY to maildesk.email_state and tag links.
    They do NOT write to providers - Gmail is enforced as read-only.
    """

    # Odoo environment (needed for bus notifications)
    env: Any

    # Email state operations
    def state_record_flags(
        self,
        account_id: int,
        folder: str,
        uid: str,
        seen: Optional[bool] = None,
        starred: Optional[bool] = None,
        source: str = "ui",
    ) -> bool: ...

    def state_record_delete(
        self, account_id: int, folder: str, uid: str, source: str = "ui"
    ) -> bool: ...

    def state_record_move(
        self,
        account_id: int,
        uid: str,
        from_folder: str,
        to_folder: str,
        source: Optional[str] = None,
    ) -> bool: ...

    # Tag operations (on message_index)
    def tag_get_all_for_account(self, account_id: int) -> List[dict]: ...

    # SSOT index lookup
    def index_message_id(self, account_id: int, folder: str, uid: str) -> str: ...

    # Index tag operations
    def index_update_tags(
        self, account_id: int, folder: str, uid: str, tag_ids: List[int]
    ) -> bool: ...

    # Folder operations
    def folder_browse(self, folder_id: int) -> Any: ...
    def folder_imap_name(self, folder: Any) -> str: ...
    def folder_name(self, folder: Any) -> str: ...

    # Message triplet resolution
    def resolve_msg_triplet(
        self, msg_id: str, folder_id: Optional[int] = None
    ) -> tuple: ...

    # Index operations
    def index_update_direct(
        self,
        index_id: int,
        is_read: Optional[bool] = None,
        is_starred: Optional[bool] = None,
    ) -> bool: ...

    def get_msg_ssot_info(self, index_id: int) -> Optional[dict]:
        """Get SSOT triplet (account_id, folder, uid) by index_id."""
        ...

    def update_folder_unread_count(self, account_id: int, folder: str) -> int:
        """Recalculate and update database unread count. Returns new count."""
        ...


@dataclass(frozen=True)
class SetFlagsParams:
    """Parameters for setting read/starred flags on messages."""

    message_ids: List[str]
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    folder_id: Optional[int] = None


@dataclass(frozen=True)
class BulkFlagsParams:
    """Parameters for bulk flag operations."""

    operations: List[dict]  # List of {ids: [...], is_read: bool, is_starred: bool}
    folder_id: Optional[int] = None


@dataclass(frozen=True)
class MoveMessagesParams:
    """Parameters for moving messages to a folder."""

    message_ids: List[str]
    target_folder_id: int


@dataclass(frozen=True)
class DeleteMessagesParams:
    """Parameters for deleting messages."""

    message_ids: List[str]
    folder_id: Optional[int] = None


@dataclass(frozen=True)
class UpdateTagsParams:
    """Parameters for updating message tags."""

    message_uids: List[str]  # Cache UIDs
    tag_ids: List[int]


class SetFlags:
    """
    Mark messages as read/unread or starred.
    """

    def __init__(
        self, deps: UIActionDeps, notifier: Optional[SSotChangeNotifier] = None
    ):
        self._deps = deps
        self._notifier = notifier

    def execute(self, params: SetFlagsParams) -> bool:
        if not params.message_ids:
            return False

        _logger.info(
            f"[SetFlags] Executing for {len(params.message_ids)} messages: "
            f"read={params.is_read}, starred={params.is_starred}"
        )

        changed_by_account_folder: Dict[Tuple[int, str], List[str]] = {}

        for msg_id in params.message_ids or []:
            try:
                # OPTIMIZATION: Use index_id directly instead of resolving triplets
                # msg_id IS the database ID of maildesk.message_index

                # Direct update on SSOT index.
                result = self._deps.index_update_direct(
                    int(msg_id),
                    is_read=params.is_read,
                    is_starred=params.is_starred,
                )

                if not result:
                    _logger.warning(
                        f"[SetFlags] Failed to update index_id={msg_id} (not found)"
                    )
                else:
                    _logger.info(
                        f"[SetFlags] Updated index_id={msg_id}: is_read={params.is_read}, is_starred={params.is_starred}"
                    )

                info = self._deps.get_msg_ssot_info(int(msg_id))
                if info:
                    key = (int(info["account_id"]), str(info["folder"]))
                    changed_by_account_folder.setdefault(key, []).append(
                        str(info["uid"])
                    )

            except Exception as e:
                _logger.error(
                    f"[SetFlags] FAILED for msg_id={msg_id}: {e}", exc_info=True
                )
                continue

        if self._notifier and (
            params.is_read is not None or params.is_starred is not None
        ):
            for (account_id, folder_name), uids in changed_by_account_folder.items():
                if not uids:
                    continue
                self._notifier.notify_flags_changed(
                    account_id=account_id,
                    folder=folder_name,
                    uids=list(dict.fromkeys(uids)),
                    is_read=params.is_read,
                    is_starred=params.is_starred,
                )

                if params.is_read is not None:
                    # Update DB consistency via dependency and GET NEW COUNT
                    new_count = self._deps.update_folder_unread_count(
                        account_id, folder_name
                    )

                    self._notifier.notify_unread_count_changed(
                        account_id=account_id,
                        folder=folder_name,
                        unread_count=new_count,
                    )

        return True


class BulkSetFlags:
    """
    Phase A use-case: Bulk set flags on multiple messages with different values.

    Writes ONLY to maildesk.email_state (UI overlay).
    Does NOT sync to provider immediately.
    """

    def __init__(
        self, deps: UIActionDeps, *, notifier: Optional[SSotChangeNotifier] = None
    ):
        self._deps = deps
        self._notifier = notifier

    def execute(self, params: BulkFlagsParams) -> bool:
        """
        Set flags in bulk operations.

        Each operation in params.operations is a dict with:
        - ids: list of message IDs
        - is_read: optional bool
        - is_starred: optional bool

        Returns True on success.
        """
        changed_by_signature: Dict[
            Tuple[int, str, Optional[bool], Optional[bool]], List[str]
        ] = {}

        for op in params.operations or []:
            is_read = op.get("is_read")
            is_starred = op.get("is_starred")
            for msg_id in op.get("ids") or []:
                acc_id, folder, uid = self._deps.resolve_msg_triplet(
                    msg_id, params.folder_id
                )
                # Write to email_state (sync journal)
                self._deps.state_record_flags(
                    acc_id,
                    folder,
                    uid,
                    seen=is_read,
                    starred=is_starred,
                    source="ui",
                )
                # CQRS projection: Update denormalized read model
                self._deps.index_update_state_projection(
                    acc_id,
                    folder,
                    uid,
                    is_read=is_read,
                    is_starred=is_starred,
                )
                changed_by_signature.setdefault(
                    (int(acc_id), str(folder), is_read, is_starred), []
                ).append(str(uid))

        if self._notifier:
            for (
                account_id,
                folder,
                is_read,
                is_starred,
            ), uids in changed_by_signature.items():
                if not uids:
                    continue
                self._notifier.notify_flags_changed(
                    account_id=account_id,
                    folder=folder,
                    uids=list(dict.fromkeys(uids)),
                    is_read=is_read,
                    is_starred=is_starred,
                )
        return True


class MoveMessages:
    """
    Phase A use-case: Move messages to a target folder.

    Writes ONLY to maildesk.email_state (UI overlay).
    Does NOT perform IMAP/provider move immediately.
    Background sync will execute the actual move.
    """

    def __init__(
        self, deps: UIActionDeps, *, notifier: Optional[SSotChangeNotifier] = None
    ):
        self._deps = deps
        self._notifier = notifier

    def execute(self, params: MoveMessagesParams) -> bool:
        """
        Record intent to move messages to target folder.

        Returns True on success.
        """
        # Get target folder name
        folder = self._deps.folder_browse(params.target_folder_id)
        to_name = (
            self._deps.folder_imap_name(folder)
            or self._deps.folder_name(folder)
            or "INBOX"
        )

        moved_by_signature: Dict[Tuple[int, str, str], List[str]] = {}

        for msg_id in params.message_ids or []:
            # Use SSOT lookup
            info = self._deps.get_msg_ssot_info(int(msg_id))
            if not info:
                continue

            acc_id = info["account_id"]
            uid = info["uid"]
            from_name = info["folder"]

            # Write to email_state (sync journal)
            self._deps.state_record_move(acc_id, uid, from_name, to_name, source="ui")
            # CQRS projection: Update denormalized read model
            self._deps.index_update_state_projection(
                acc_id, from_name, uid, pending_move_to=to_name
            )
            moved_by_signature.setdefault(
                (int(acc_id), str(from_name), str(to_name)), []
            ).append(str(uid))

        if self._notifier:
            for (
                account_id,
                source_folder,
                destination_folder,
            ), uids in moved_by_signature.items():
                if not uids:
                    continue
                self._notifier.notify_messages_moved(
                    account_id=account_id,
                    source_folder=source_folder,
                    destination_folder=destination_folder,
                    uids=list(dict.fromkeys(uids)),
                )
        return True


class DeleteMessages:
    """
    Phase A use-case: Delete messages.

    Writes ONLY to maildesk.email_state (UI overlay).
    Does NOT delete from provider immediately.
    Background sync will execute the actual deletion.
    """

    def __init__(
        self, deps: UIActionDeps, *, notifier: Optional[SSotChangeNotifier] = None
    ):
        self._deps = deps
        self._notifier = notifier

    def execute(self, params: DeleteMessagesParams) -> bool:
        """
        Record intent to delete messages.

        Returns True on success.
        """
        deleted_by_account_folder: Dict[Tuple[int, str], List[str]] = {}

        for msg_id in params.message_ids or []:
            # Use SSOT lookup
            info = self._deps.get_msg_ssot_info(int(msg_id))
            if not info:
                continue

            acc_id = info["account_id"]
            folder = info["folder"]
            uid = info["uid"]

            # Write to email_state (sync journal)
            self._deps.state_record_delete(acc_id, folder, uid, source="ui")
            # CQRS projection: Update denormalized read model
            self._deps.index_update_state_projection(
                acc_id, folder, uid, pending_delete=True
            )
            deleted_by_account_folder.setdefault((int(acc_id), str(folder)), []).append(
                str(uid)
            )

        if self._notifier:
            for (account_id, folder), uids in deleted_by_account_folder.items():
                if not uids:
                    continue
                self._notifier.notify_messages_deleted(
                    account_id=account_id,
                    folder=folder,
                    uids=list(dict.fromkeys(uids)),
                )
        return True


class UpdateTags:
    """
    Phase A use-case: Update tags associated with messages.

    Writes ONLY to maildesk.message_index.tag_ids (SSOT).
    Does NOT sync to provider (tags are local-only).
    """

    def __init__(
        self, deps: UIActionDeps, *, notifier: Optional[SSotChangeNotifier] = None
    ):
        self._deps = deps
        self._notifier = notifier

    def execute(self, params: UpdateTagsParams) -> bool:
        """
        Update tags for messages.

        Params:
        - message_uids: List of cache UIDs
        - tag_ids: List of tag IDs to assign

        Returns True on success.
        """

        if not params.message_uids:
            return True

        # Track changed messages by account+folder for bus events
        changed_by_account_folder: Dict[Tuple[int, str], List[str]] = {}
        failed_updates = []

        for uid in params.message_uids:
            try:
                info = self._deps.get_msg_ssot_info(int(uid))
            except (ValueError, TypeError):
                info = None

            if not info:
                failed_updates.append(uid)
                _logger.warning(f"[UpdateTags] Message index_id={uid} not found")
                continue

            acc_id = info["account_id"]
            folder = info["folder"]
            msg_uid = info["uid"]

            # Update tags directly in SSOT index
            # Returns dict with tags on success, None on failure
            result = self._deps.index_update_tags(
                acc_id, folder, str(msg_uid), params.tag_ids
            )

            if not result:
                failed_updates.append(uid)
                _logger.error(
                    f"[UpdateTags] Failed to update tags for index_id={uid} (account={acc_id}, folder={folder}, uid={msg_uid})"
                )
                continue

            # Track for bus events (only if update succeeded)
            key = (int(acc_id), str(folder))
            changed_by_account_folder.setdefault(key, []).append(str(msg_uid))

        # Emit bus events (same pattern as SetFlags)
        if self._notifier:
            for (account_id, folder), uids in changed_by_account_folder.items():
                if not uids:
                    continue
                self._notifier.notify_tags_changed(
                    account_id=account_id,
                    folder=folder,
                    uids=list(dict.fromkeys(uids)),
                    tag_ids=params.tag_ids,
                )

        if failed_updates:
            _logger.warning(
                f"[UpdateTags] Failed to update {len(failed_updates)} message(s): {failed_updates}"
            )

        return len(failed_updates) == 0
