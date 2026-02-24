# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Application-layer contract for SSOT change notifications.

This module defines the Protocol that use cases depend on for notifying
about SSOT mutations. Implementations live in the infrastructure layer.

ARCHITECTURAL RULES:
- This Protocol MUST NOT depend on infrastructure (bus, Odoo, SQL)
- This Protocol represents business events, not technical events
- Use cases inject this dependency via constructor
- Infrastructure provides concrete implementations
"""

from __future__ import annotations

from typing import List, Optional, Protocol


class SSotChangeNotifier(Protocol):
    """
    Protocol for notifying about SSOT (maildesk.message_index) mutations.

    This abstraction allows use cases to emit events without depending on
    infrastructure details (Odoo bus, websockets, etc.).

    All methods follow the Command pattern and return None.
    Infrastructure implementations should log emissions for observability.
    """

    def notify_flags_changed(
        self,
        account_id: int,
        folder: str,
        uids: List[str],
        *,
        index_ids: Optional[List[int]] = None,
        is_read: Optional[bool] = None,
        is_starred: Optional[bool] = None,
    ) -> None:
        """
        Notify that message flags have changed in SSOT.

        Called when: IMAP FLAGS update detected and persisted to message_index
        Expected UI behavior: Update read/starred icons without full refresh

        Args:
            account_id: Account identifier
            folder: Folder name (e.g., "INBOX")
            uids: List of message UIDs affected
            index_ids: Optional SSOT ids (preferred for deterministic matching)
            is_read: New read state if changed (None = not changed)
            is_starred: New starred state if changed (None = not changed)

        Example:
            notifier.notify_flags_changed(
                account_id=42,
                folder="INBOX",
                uids=["567", "568"],
                is_read=True
            )
        """
        ...

    def notify_messages_added(
        self,
        account_id: int,
        folder: str,
        uids: List[str],
        *,
        origin: str,
        index_ids: Optional[List[int]] = None,
        messages: Optional[List[dict]] = None,
    ) -> None:
        """
        Notify that new messages have been added to SSOT.

        Called when: SSOT has been updated with new messages.
        Expected UI behavior: Refresh affected folder(s) from SSOT.

        Important:
        - This is a *domain event* ("SSOT changed"), not a UI decision.
        - Desktop notifications are gated in infrastructure (presence + policy)
          and MUST NOT be queued/replayed.

        Args:
            account_id: Account identifier
            folder: Folder name where messages were added
            uids: List of new message UIDs
            origin: Source of the change (e.g. "imap_incremental", "send_email")
            index_ids: Optional SSOT ids for deduplication (preferred over uid/message_id).
            messages: Optional list of message summaries for *realtime* notifications.
                Each dict should contain: index_id (preferred), message_id, uid,
                subject, preview, sender_name, date.

        Example:
            notifier.notify_messages_added(
                account_id=42,
                folder="INBOX",
                uids=["1001", "1002"],
                origin="imap_incremental",
                index_ids=[123, 124],
                messages=[{
                    "index_id": 123,
                    "uid": "1001",
                    "subject": "Meeting tomorrow",
                    "preview": "Let's meet at 10am...",
                    "sender_name": "John Doe",
                    "date": "2026-01-09T10:00:00Z"
                }]
            )
        """
        ...

    def notify_messages_moved(
        self,
        account_id: int,
        source_folder: str,
        destination_folder: str,
        uids: List[str],
    ) -> None:
        """
        Notify that messages have moved between folders in SSOT.

        Called when: Messages detected in different folder than indexed
        Expected UI behavior: Remove from source list, add to destination list

        Args:
            account_id: Account identifier
            source_folder: Original folder name
            destination_folder: New folder name
            uids: List of moved message UIDs

        Note: Currently deferred - requires IMAP COPY detection logic
        """
        ...

    def notify_tags_changed(
        self, account_id: int, folder: str, uids: List[str], tags: List[dict]
    ) -> None:
        """Notify that tags have changed for messages."""
        ...

    def notify_unread_count_changed(
        self, account_id: int, folder: str, unread_count: int
    ) -> None:
        """Notify that unread count has changed (absolute value)."""
        ...

    def notify_messages_deleted(
        self,
        account_id: int,
        folder: str,
        uids: List[str],
    ) -> None:
        """
        Notify that messages have been deleted from server.

        Called when: EXPUNGE detected or deleted_on_server flag set
        Expected UI behavior: Remove messages from list

        Args:
            account_id: Account identifier
            folder: Folder name where messages were deleted
            uids: List of deleted message UIDs

        Note: Currently deferred - requires EXPUNGE reconciliation logic
        """
        ...

    def notify_full_refresh(
        self,
        account_id: int,
        folder: Optional[str] = None,
    ) -> None:
        """
        Request full UI refresh of message list.

        Called when: UIDVALIDITY change, major sync errors, or fallback
        Expected UI behavior: Re-fetch entire folder contents

        Args:
            account_id: Account identifier
            folder: Specific folder to refresh (None = all folders)

        Example:
            # UIDVALIDITY changed - folder reset
            notifier.notify_full_refresh(
                account_id=42,
                folder="INBOX"
            )
        """
        ...

    def notify_folder_tree_changed(
        self,
        account_id: int,
        folders: List[dict],
    ) -> None:
        """
        Notify that folder structure has changed.

        Called when: IMAP folder discovery detects new/renamed/deleted folders
        Expected UI behavior: Refresh folder tree only (no message reload)

        Args:
            account_id: Account identifier
            folders: Minimal folder metadata [{"id": 1, "name": "INBOX", ...}, ...]
                Each dict contains: id, name, imap_name (minimal data only)

        Example:
            notifier.notify_folder_tree_changed(
                account_id=42,
                folders=[
                    {"id": 1, "name": "Inbox", "imap_name": "INBOX"},
                    {"id": 2, "name": "Drafts", "imap_name": "Drafts"},
                ]
            )
        """
        ...
