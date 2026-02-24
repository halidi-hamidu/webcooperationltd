# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Bus Orchestrator.

Defines Odoo ORM models and server-side APIs for Bus Orchestrator.
Layer: odoo models.
"""

import logging

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import AccessError


_logger = logging.getLogger(__name__)


class BusOrchestrator(models.AbstractModel):
    _name = "maildesk.bus_orchestrator"
    _description = "MailDesk Bus Orchestrator"

    @api.model
    def dispatch(self, channel, notification_type, payload):
        """
        Orchestration boundary for all bus emissions.
        Centralizes event dispatch to ensure consistency and debugging.
        """
        if isinstance(channel, str):
            raise AccessError(
                self.env._(
                    "MailDesk bus target must not be a string channel (security)."
                )
            )

        if not hasattr(channel, "_name"):
            raise AccessError(
                self.env._("MailDesk bus target must be a recordset channel.")
            )

        allowed_targets = {"mailbox.account", "res.users"}
        if channel._name not in allowed_targets:
            msg = self.env._(
                "MailDesk bus target must be one of %(allowed)s, got %(got)s."
            )
            raise AccessError(
                msg
                % {
                    "allowed": ", ".join(sorted(allowed_targets)),
                    "got": channel._name,
                }
            )

        is_admin = self.env.uid == SUPERUSER_ID or self.env.user.has_group(
            "maildesk_mail_client.group_mailbox_admin"
        )

        # Access enforcement:
        # - mailbox.account events are account-scope: user must have access_user_ids
        # - res.users events are user-scope: non-admin can only target self
        if channel._name == "mailbox.account" and not is_admin:
            unauthorized = channel.filtered(
                lambda a: self.env.user not in a.access_user_ids
            )
            if unauthorized:
                raise AccessError(
                    self.env._(
                        "You do not have access to emit bus notifications for this mailbox account."
                    )
                )
        if channel._name == "res.users" and not is_admin:
            if channel.ids != [self.env.uid]:
                raise AccessError(
                    self.env._("You can only emit user notifications for yourself.")
                )

        _logger.info(
            "[MailDesk Bus] emit: type=%s target=%s(%s) payload_keys=%s",
            notification_type,
            channel._name,
            ",".join(map(str, channel.ids)),
            sorted((payload or {}).keys()),
        )
        self.env["bus.bus"]._sendone(channel, notification_type, payload)

    @api.model
    def _account_bus_target(self, account_id: int):
        """
        Return the secure bus target for a mailbox account.

        We intentionally use a recordset channel (not a string channel) so the
        websocket subscription can be access-gated in `ir.websocket` and so we
        do not rely on unguessable string targets.
        """
        account = self.env["mailbox.account"].browse(int(account_id))
        return account if account.exists() else None

    @api.model
    def notify_messages_added(self, account_id, folder, uids):
        """Standardized SSOT event for new messages (UI refresh only)."""
        target = self._account_bus_target(account_id)
        if not target:
            return
        payload = {
            "account_id": int(account_id),
            "folder": folder,
            "uids": uids,
            "count": len(uids),
        }
        self.dispatch(target, "maildesk.account/messages_added", payload)

    @api.model
    def notify_flags_changed(self, account_id, folder, uids, flags, index_ids=None):
        """Standardized event for flag changes."""
        target = self._account_bus_target(account_id)
        if not target:
            return
        payload = {
            "account_id": int(account_id),
            "folder": folder,
            "uids": uids,
            "index_ids": index_ids or [],
            "flags": flags,
        }
        self.dispatch(target, "maildesk.account/flags_changed", payload)

    @api.model
    def notify_messages_moved(
        self, account_id, source_folder, destination_folder, uids
    ):
        """Standardized event for message moves."""
        target = self._account_bus_target(account_id)
        if not target:
            return
        payload = {
            "account_id": int(account_id),
            "source_folder": source_folder,
            "destination_folder": destination_folder,
            "uids": uids,
            "count": len(uids),
        }
        self.dispatch(target, "maildesk.account/messages_moved", payload)

    @api.model
    def notify_messages_deleted(self, account_id, folder, uids):
        """Standardized event for message deletions."""
        target = self._account_bus_target(account_id)
        if not target:
            return
        payload = {
            "account_id": int(account_id),
            "folder": folder,
            "uids": uids,
            "count": len(uids),
        }
        self.dispatch(target, "maildesk.account/messages_deleted", payload)

    @api.model
    def notify_refresh(self, account_id, folder=None):
        """Standardized event for UI refresh (pull latest SSOT)."""
        target = self._account_bus_target(account_id)
        if not target:
            return
        payload = {
            "account_id": int(account_id),
            "folder": folder,
        }
        self.dispatch(target, "maildesk.account/refresh", payload)

    @api.model
    def notify_full_refresh(self, account_id, folder=None):
        """Backward-compatible alias."""
        return self.notify_refresh(account_id, folder=folder)

    @api.model
    def _user_bus_target(self, user_id: int):
        user = self.env["res.users"].browse(int(user_id))
        return user if user.exists() else None

    @api.model
    def notify_user_new_messages(self, user_id: int, payload: dict) -> None:
        """
        Real-time user notification event (desktop notifications).

        Target: res.users(<id>) recordset channel (subscribed via 'maildesk.user').
        Type: maildesk.notify/new_messages
        """
        target = self._user_bus_target(user_id)
        if not target:
            return
        self.dispatch(target, "maildesk.notify/new_messages", payload)

    @api.model
    def notify_folder_tree_changed(self, account_id, folders):
        """Standardized event for folder tree changes."""
        target = self._account_bus_target(account_id)
        if not target:
            return
        payload = {
            "account_id": int(account_id),
            "folders": folders,  # Minimal: [{"id": 1, "name": "...", "imap_name": "..."}, ...]
        }
        self.dispatch(target, "maildesk.account/folder_tree_changed", payload)

    @api.model
    def notify_tags_changed(self, account_id, folder, uids, tags):
        """
        Standardized event for tag changes.

        Args:
            tags: List of tag dicts with {id, name, color}
        """
        target = self._account_bus_target(account_id)
        if not target:
            return
        payload = {
            "account_id": int(account_id),
            "folder": folder,
            "uids": uids,
            "tags": tags,  # Full tag objects, not just IDs
            "count": len(uids),
        }
        self.dispatch(target, "maildesk.account/tags_changed", payload)

    @api.model
    def notify_unread_count_changed(self, account_id, folder, unread_count):
        """
        Notify frontend of absolute unread count change.
        """
        target = self._account_bus_target(account_id)
        if not target:
            return
        payload = {
            "account_id": int(account_id),
            "folder": folder,
            "count": int(unread_count),
        }
        self.dispatch(target, "maildesk.account/unread_count_changed", payload)
