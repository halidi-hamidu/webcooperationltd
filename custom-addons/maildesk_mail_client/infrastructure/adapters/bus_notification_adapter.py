# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Infrastructure adapter implementing SSotChangeNotifier via Odoo bus.

This module provides the concrete implementation of the SSotChangeNotifier
Protocol using Odoo's bus infrastructure for real-time event propagation.

ARCHITECTURAL RULES:
- Lives in infrastructure layer
- Depends on Odoo environment (acceptable here)
- Implements Protocol from domain layer
- Logs all emissions for observability
"""

import logging
import time
from typing import List, Optional

from odoo import fields

_logger = logging.getLogger(__name__)


class BusNotificationAdapter:
    """
    Concrete implementation of SSotChangeNotifier using Odoo bus.

    This adapter translates domain-level notification calls into
    Odoo bus events that are delivered to frontend via websocket.

    Architecture:
        Use Case → SSotChangeNotifier Protocol → BusNotificationAdapter
        → BusOrchestrator → Odoo Bus → WebSocket → Frontend

    Usage:
        notifier = BusNotificationAdapter(env)
        use_case = SomeUseCase(env, notifier=notifier)
    """

    def __init__(self, env):
        """
        Initialize adapter with Odoo environment.

        Args:
            env: Odoo environment (infrastructure dependency)
        """
        self.env = env

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
        Emit bus event for flag changes.

        Target: mailbox.account record channel (access-gated in ir.websocket)
        Notification type: maildesk.account/flags_changed
        """
        if not uids:
            return

        # Validation: ensure we never emit None for flags.
        # None is only allowed if BOTH flags are None (defensive fallback)
        # But ideally, callers should ALWAYS provide actual flag values
        if is_read is None and is_starred is None:
            _logger.error(
                f"[BusNotification] INVALID flags_changed event: "
                f"Both is_read and is_starred are None! "
                f"account={account_id}, folder={folder}, uids={uids[:3]}..."
            )
            # Fallback: emit refresh event instead of invalid flag change
            BusOrch = self.env["maildesk.bus_orchestrator"]
            BusOrch.notify_refresh(account_id=account_id, folder=folder)
            return

        # Use existing BusOrchestrator infrastructure
        BusOrch = self.env["maildesk.bus_orchestrator"]
        BusOrch.notify_flags_changed(
            account_id=account_id,
            folder=folder,
            uids=uids,
            index_ids=index_ids or [],
            flags={"is_read": is_read, "is_starred": is_starred},
        )

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
        Emit SSOT change event for new messages and (optionally) real-time user notifications.

        Target: mailbox.account record channel (access-gated in ir.websocket)
        Notification type: maildesk.account/messages_added

        Desktop notifications are sent as a separate per-user event and are gated:
        - Only for visible folders (not Sent/Drafts/Trash/Spam/Archive)
        - Only when the folder is being synced in 'realtime' mode (no catchup bursts)
        - Only for users who currently have MailDesk open (presence ping)
        - Never replayed (frontend drops stale events on reconnect)
        """
        if not uids:
            return

        BusOrch = self.env["maildesk.bus_orchestrator"]
        BusOrch.notify_messages_added(
            account_id=account_id,
            folder=folder,
            uids=uids,
        )

        self._maybe_notify_users_new_messages(
            account_id=account_id,
            folder=folder,
            origin=origin,
            index_ids=index_ids or [],
            messages=messages or [],
        )

    # ---------------------------------------------------------------------
    # Desktop notifications (realtime only; never queued/replayed)
    # ---------------------------------------------------------------------

    def _maybe_notify_users_new_messages(
        self,
        *,
        account_id: int,
        folder: str,
        origin: str,
        index_ids: List[int],
        messages: List[dict],
    ) -> None:
        if not index_ids or not messages:
            return

        # Resolve folder metadata (visibility/type/last_sync_at) without leaking recordsets upward.
        Folder = self.env["mailbox.folder"].sudo()
        folder_rec = Folder.search(
            [("account_id", "=", int(account_id)), ("imap_name", "=", folder)],
            limit=1,
        )
        if not folder_rec:
            folder_rec = Folder.search(
                [("account_id", "=", int(account_id)), ("name", "=", folder)],
                limit=1,
            )
        if not folder_rec:
            return

        if not folder_rec.is_visible:
            return
        if folder_rec.folder_type in {"sent", "drafts", "trash", "spam", "archive"}:
            return

        # Catchup suppression: if the folder wasn't syncing recently, do not emit desktop notifications.
        # This prevents bursts after reconnect/offline periods.
        now = fields.Datetime.now()
        last_sync_at = folder_rec.last_sync_at
        realtime_gap_seconds = 120
        if not last_sync_at:
            return
        gap = (now - last_sync_at).total_seconds()
        if gap > realtime_gap_seconds:
            _logger.info(
                "[MailDesk Notify] suppressed (catchup): account=%s folder=%s gap_s=%s",
                account_id,
                folder,
                int(gap),
            )
            return

        # Only notify users who currently have MailDesk open.
        Account = self.env["mailbox.account"].sudo()
        account = Account.browse(int(account_id))
        if not account.exists():
            return
        recipient_user_ids = account.access_user_ids.ids
        if not recipient_user_ids:
            return

        presence_max_age_seconds = 90
        online_user_ids = set(
            self.env["maildesk.ui_presence"]
            .sudo()
            .online_user_ids(
                recipient_user_ids, max_age_seconds=presence_max_age_seconds
            )
        )
        if not online_user_ids:
            return

        # Hard cap to prevent notification bursts in a single sync iteration.
        max_per_event = 3
        notify_messages = messages[:max_per_event]
        emitted_at_dt = fields.Datetime.now()  # naive UTC in Odoo
        emitted_at = emitted_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        emitted_at_ms = int(time.time() * 1000)

        payload = {
            "emitted_at": emitted_at,
            "emitted_at_ms": emitted_at_ms,
            "account_id": int(account_id),
            "folder": folder,
            "count": len(index_ids),
            "messages": notify_messages,
        }

        for user_id in sorted(online_user_ids):
            self.env["maildesk.bus_orchestrator"].notify_user_new_messages(
                int(user_id), payload
            )

    def notify_messages_moved(
        self,
        account_id: int,
        source_folder: str,
        destination_folder: str,
        uids: List[str],
    ) -> None:
        """
        Emit bus event for folder moves.

        Target: mailbox.account record channel (access-gated in ir.websocket)
        Notification type: maildesk.account/messages_moved
        """
        if not uids:
            return

        BusOrch = self.env["maildesk.bus_orchestrator"]
        BusOrch.notify_messages_moved(
            account_id=account_id,
            source_folder=source_folder,
            destination_folder=destination_folder,
            uids=uids,
        )

    def notify_messages_deleted(
        self,
        account_id: int,
        folder: str,
        uids: List[str],
    ) -> None:
        """
        Emit bus event for message deletions.

        Target: mailbox.account record channel (access-gated in ir.websocket)
        Notification type: maildesk.account/messages_deleted
        """
        if not uids:
            return

        BusOrch = self.env["maildesk.bus_orchestrator"]
        BusOrch.notify_messages_deleted(
            account_id=account_id,
            folder=folder,
            uids=uids,
        )

    def notify_full_refresh(
        self,
        account_id: int,
        folder: Optional[str] = None,
    ) -> None:
        """
        Emit bus event requesting full refresh.

        Target: mailbox.account record channel (access-gated in ir.websocket)
        Notification type: maildesk.account/refresh
        """
        BusOrch = self.env["maildesk.bus_orchestrator"]
        BusOrch.notify_refresh(account_id=account_id, folder=folder)

    def notify_folder_tree_changed(
        self,
        account_id: int,
        folders: List[dict],
    ) -> None:
        """
        Emit bus event for folder tree changes.

        Target: mailbox.account record channel (access-gated in ir.websocket)
        Notification type: maildesk.account/folder_tree_changed

        Frontend will refresh folder tree only (no message reload).
        """
        BusOrch = self.env["maildesk.bus_orchestrator"]
        BusOrch.notify_folder_tree_changed(
            account_id=account_id,
            folders=folders,
        )

    def notify_tags_changed(
        self,
        account_id: int,
        folder: str,
        uids: List[str],
        tag_ids: List[int],
    ) -> None:
        """
        Emit bus event for tag changes.

        Target: mailbox.account record channel (access-gated in ir.websocket)
        Notification type: maildesk.account/tags_changed

        Frontend will update tag display for affected messages.
        """
        if not uids:
            return

        # Fetch full tag objects from database
        tags = []
        if tag_ids:
            TagModel = self.env["mail.message.tag"]
            tag_records = TagModel.browse(tag_ids)
            tags = [
                {"id": t.id, "name": t.name, "color": t.color}
                for t in tag_records
                if t.exists()
            ]

        BusOrch = self.env["maildesk.bus_orchestrator"]
        BusOrch.notify_tags_changed(
            account_id=account_id,
            folder=folder,
            uids=uids,
            tags=tags,  # Full tag objects
        )

    def notify_unread_count_changed(
        self, account_id: int, folder: str, unread_count: int
    ) -> None:
        """
        Notify frontend of unread count change (absolute).
        """
        BusOrch = self.env["maildesk.bus_orchestrator"]
        BusOrch.notify_unread_count_changed(
            account_id=account_id,
            folder=folder,
            unread_count=unread_count,
        )
