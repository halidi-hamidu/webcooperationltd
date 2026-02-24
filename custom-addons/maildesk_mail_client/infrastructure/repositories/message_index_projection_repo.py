# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
MessageIndexProjectionRepo: Write-side CQRS projection repository

Isolates all ORM mutations for message_index from UI actions.
This is the ONLY layer allowed to call env["maildesk.message_index"] for writes.
"""


class MessageIndexProjectionRepo:
    """
    Repository for projecting UI actions into message_index denormalized read model.

    Responsibilities:
    - Update is_read, is_starred flags
    - Update pending_move_to, pending_delete projections
    - Update denormalized tag_ids
    - Find message_index records by natural key

    Clean Architecture:
    - Adapters call this repository (no direct ORM access)
    - Use cases don't know about this (depend on protocols only)
    """

    def __init__(self, env):
        """
        Args:
            env: Odoo environment (injected by adapter)
        """
        self._env = env

    def update_state_projection(
        self,
        account_id,
        folder,
        uid,
        is_read=None,
        is_starred=None,
        pending_move_to=None,
        pending_delete=None,
        index_id=None,
    ):
        """
        Project state changes from UI actions into denormalized read model.

        Args:
            account_id: Account ID
            folder: Folder name
            uid: Message UID
            is_read: Optional boolean for read state
            is_starred: Optional boolean for starred state
            pending_move_to: Optional target folder name for pending move
            pending_delete: Optional boolean for pending delete
            index_id: Optional record ID (bypasses triplet search)

        Returns:
            True if record found and updated, False otherwise
        """
        Index = self._env["maildesk.message_index"].sudo()
        return Index.update_state_projection(
            account_id,
            folder,
            uid,
            is_read=is_read,
            is_starred=is_starred,
            pending_move_to=pending_move_to,
            pending_delete=pending_delete,
            index_id=index_id,
        )

    def update_tags(self, account_id, folder, uid, tag_ids):
        """
        Project tag changes from UI action into denormalized read model.

        Args:
            account_id: Account ID
            folder: Folder name
            uid: Message UID
            tag_ids: List of tag IDs to assign (replaces all existing)

        Returns:
            True if record found and updated, False otherwise
        """
        Index = self._env["maildesk.message_index"].sudo()
        return Index.update_tags(account_id, folder, uid, tag_ids)

    def find_by_triplet(self, account_id, folder, uid):
        """
        Find message_index record by natural key (account/folder/uid).

        Args:
            account_id: Account ID
            folder: Folder name
            uid: Message UID

        Returns:
            message_index recordset (empty if not found)
        """
        Index = self._env["maildesk.message_index"].sudo()
        return Index.find_by_triplet(account_id, folder, uid)
