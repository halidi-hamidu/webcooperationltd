# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Email State Repository: Encapsulates all ORM access to maildesk.email_state.
Provides clean interface for recording state mutations (flags, moves, deletes).

Enforces mutation policy to prevent unauthorized writes.
"""

from ...domain.policies.mutation_policy import MutationPolicy


class EmailStateRepository:
    """Repository for email state persistence operations."""

    def __init__(self, env):
        self._env = env
        self._state_model = env["maildesk.email_state"].sudo()

    def record_flags(
        self,
        account_id,
        folder,
        uid,
        seen=None,
        starred=None,
        source="ui",
        mutation_context=None,
    ):
        """
        Record flag changes for a message.

        Args:
            account_id: Account ID
            folder: Folder name
            uid: Message UID
            seen: Read status (None to not change)
            starred: Star status (None to not change)
            source: Source of the change (ui, sync, etc.)
            mutation_context: Mutation context for policy enforcement
        """
        if mutation_context:
            MutationPolicy.validate_email_state_write(mutation_context)
        return self._state_model.record_flags(
            account_id, folder, uid, seen=seen, starred=starred, source=source
        )

    def record_delete(
        self, account_id, folder, uid, source="ui", mutation_context=None
    ):
        """
        Record message deletion.

        Args:
            account_id: Account ID
            folder: Folder name
            uid: Message UID
            source: Source of the deletion
            mutation_context: Mutation context for policy enforcement
        """
        if mutation_context:
            MutationPolicy.validate_email_state_write(mutation_context)
        return self._state_model.record_delete(account_id, folder, uid, source=source)

    def record_move(
        self,
        account_id,
        uid,
        from_folder,
        to_folder,
        source=None,
        mutation_context=None,
    ):
        """
        Record message move between folders.

        Args:
            account_id: Account ID
            uid: Message UID
            from_folder: Source folder name
            to_folder: Target folder name
            source: Source of the move
            mutation_context: Mutation context for policy enforcement
        """
        if mutation_context:
            MutationPolicy.validate_email_state_write(mutation_context)
        return self._state_model.record_move(
            account_id, uid, from_folder, to_folder, source=source
        )
