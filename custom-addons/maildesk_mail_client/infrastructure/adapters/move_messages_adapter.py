# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Move Messages Adapter.

Implements infrastructure integration for Move Messages Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from ..utils.message_resolver import resolve_message_triplet


class MoveMessagesAdapter:
    """
    Adapter for MoveMessages and DeleteMessages use cases.

    Clean Architecture compliant:
    - Injects MessageIndexProjectionRepo
    - No direct ORM access
    """

    def __init__(self, env, state_repo, mutation_context, projection_repo):
        """
        Args:
            env: Odoo environment
            state_repo: Email state repository
            mutation_context: Mutation tracking context
            projection_repo: MessageIndexProjectionRepo
        """
        self.env = env
        self._sync = env["mailbox.sync"]
        self._state_repo = state_repo
        self._mutation_context = mutation_context
        self._projection_repo = projection_repo

    def state_record_move(self, account_id, uid, from_folder, to_folder, source=None):
        """Write move intent to email_state sync journal."""
        return self._state_repo.record_move(
            account_id,
            uid,
            from_folder,
            to_folder,
            source,
            self._mutation_context,
        )

    def state_record_delete(self, account_id, folder, uid, source="ui"):
        """Write delete intent to email_state sync journal."""
        return self._state_repo.record_delete(
            account_id, folder, uid, source, self._mutation_context
        )

    def index_update_state_projection(
        self, account_id, folder, uid, pending_move_to=None, pending_delete=None
    ):
        """
        CQRS projection: Update message_index pending operation fields.

        Clean Architecture: Delegates to repository.
        """
        return self._projection_repo.update_state_projection(
            account_id,
            folder,
            uid,
            pending_move_to=pending_move_to,
            pending_delete=pending_delete,
        )

    def resolve_msg_triplet(self, msg_id, folder_id=None):
        return resolve_message_triplet(msg_id, folder_id, self.env)

    def folder_browse(self, folder_id):
        return self.env["mailbox.folder"].browse(folder_id)

    def folder_imap_name(self, folder):
        return folder.imap_name

    def folder_name(self, folder):
        return folder.name

    def get_msg_ssot_info(self, index_id: int):
        """Get account_id, folder, uid from message_index."""
        rec = self.env["maildesk.message_index"].browse(int(index_id))
        if not rec.exists():
            return None
        return {
            "account_id": rec.account_id.id,
            "folder": rec.folder,
            "uid": rec.uid,
            "message_id": rec.message_id,
        }
