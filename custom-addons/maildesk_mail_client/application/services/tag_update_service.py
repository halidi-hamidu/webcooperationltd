# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)

"""
TagUpdateService: Handles tag updates on different entity types.

Layer: application service
"""

from typing import Any, List, Optional


class TagUpdateService:
    """Service for updating tags on drafts and message_index."""

    def __init__(self, env: Any):
        """
        Initialize service.

        Args:
            env: Odoo environment
        """
        self._env = env

    def update_draft_tags(self, draft_id: int, tag_ids: List[int]) -> Optional[dict]:
        """
        Update tags on a draft.

        Args:
            draft_id: Draft ID
            tag_ids: List of tag IDs

        Returns:
            Dict with tags on success, None on failure
        """
        try:
            Draft = self._env["maildesk.draft"].sudo()
            draft = Draft.browse(draft_id)
            if not draft.exists():
                return None

            draft.write({"tag_ids": [(6, 0, tag_ids)]})

            return {
                "tags": [
                    {"id": t.id, "name": t.name, "color": t.color}
                    for t in draft.tag_ids
                ]
            }
        except Exception:
            return None

    def update_index_tags(
        self, account_id: int, folder: str, uid: str, tag_ids: List[int]
    ) -> Optional[dict]:
        """
        Update tags on a message_index entry.

        Args:
            account_id: Account ID
            folder: Folder name
            uid: Message UID
            tag_ids: List of tag IDs

        Returns:
            Dict with tags on success, None on failure
        """
        Index = self._env["maildesk.message_index"].sudo()
        return Index.update_tags(account_id, folder, uid, tag_ids)
