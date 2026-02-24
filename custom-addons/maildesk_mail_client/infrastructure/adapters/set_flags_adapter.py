# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Set Flags Adapter.

Implements infrastructure integration for Set Flags Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from typing import Optional
from ..utils.message_resolver import resolve_message_triplet


class SetFlagsAdapter:
    """
    Adapter for SetFlags use case.

    Clean Architecture compliant:
    - Injects MessageIndexProjectionRepo (no direct ORM access)
    - Adapter is wiring layer only
    """

    def __init__(self, env, state_repo, mutation_context, projection_repo):
        """
        Args:
            env: Odoo environment
            state_repo: Email state repository (for sync journal)
            mutation_context: Mutation tracking context
            projection_repo: MessageIndexProjectionRepo (for CQRS projection)
        """
        self.env = env
        self._sync = env["mailbox.sync"]
        self._state_repo = state_repo
        self._mutation_context = mutation_context
        self._projection_repo = projection_repo

    def state_record_flags(
        self, account_id, folder, uid, seen=None, starred=None, source="ui"
    ):
        """Write to email_state sync journal."""
        return self._state_repo.record_flags(
            account_id,
            folder,
            uid,
            seen,
            starred,
            source,
            self._mutation_context,
        )

    def index_update_state_projection(
        self, account_id, folder, uid, is_read=None, is_starred=None
    ):
        """
        CQRS projection: Update message_index denormalized state fields.

        Clean Architecture: Delegates to repository (no ORM knowledge).
        """
        return self._projection_repo.update_state_projection(
            account_id, folder, uid, is_read=is_read, is_starred=is_starred
        )

    def resolve_msg_triplet(self, msg_id, folder_id=None):
        return resolve_message_triplet(msg_id, folder_id, self.env)

    def index_update_direct(self, index_id, is_read=None, is_starred=None):
        """
        Directly update index record via browse/write.

        This bypasses triplet resolution and relies on the index_id from UI.
        The message_index.write() method handles sync propagation.
        """
        rec = self.env["maildesk.message_index"].sudo().browse(int(index_id))
        if not rec.exists():
            return False

        vals = {}
        if is_read is not None:
            vals["is_read"] = is_read
        if is_starred is not None:
            vals["is_starred"] = is_starred

        if vals:
            rec.write(vals)
            return True
        return True

    def get_msg_ssot_info(self, index_id: int) -> Optional[dict]:
        """Get account_id, folder, uid from message_index."""
        rec = self.env["maildesk.message_index"].sudo().browse(int(index_id))
        if not rec.exists():
            return None
        return {
            "account_id": rec.account_id.id,
            "folder": rec.folder,
            "uid": rec.uid,
            "message_id": rec.message_id,
        }

    def update_folder_unread_count(self, account_id: int, folder: str) -> int:
        """
        Recalculate and update database unread count for consistency.
        Implements UIActionDeps dependency.
        Returns the new unread count.
        """
        Index = self.env["maildesk.message_index"].sudo()
        Folder = self.env["mailbox.folder"].sudo()

        count = Index.search_count(
            [
                ("account_id", "=", account_id),
                ("folder", "=", folder),
                ("is_read", "=", False),
            ]
        )

        folder_rec = Folder.search(
            [
                ("account_id", "=", account_id),
                ("imap_name", "=", folder),
            ],
            limit=1,
        )

        if folder_rec:
            folder_rec.write(
                {"unread_count": count, "unread_count_updated_at": self.env.cr.now()}
            )

        return count
