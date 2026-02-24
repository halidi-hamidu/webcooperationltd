# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)

"""
MessageIndexRepository: Encapsulates ORM access to maildesk.message_index.

Layer: infrastructure
"""

from typing import Any, List, Optional


class MessageIndexRepository:
    """Repository for message_index persistence operations."""

    def __init__(self, env: Any):
        """
        Initialize repository.

        Args:
            env: Odoo environment
        """
        self._env = env
        self._model = env["maildesk.message_index"].sudo()

    def browse(self, index_id: int) -> Any:
        """
        Browse message_index by ID.

        Args:
            index_id: message_index ID

        Returns:
            message_index record
        """
        return self._model.browse(int(index_id))

    def exists(self, record: Any) -> bool:
        """
        Check if record exists.

        Args:
            record: message_index record

        Returns:
            True if exists
        """
        return bool(record and record.exists())

    def get_by_id(self, index_id: int) -> Optional[Any]:
        """
        Get message_index by ID if exists.

        Args:
            index_id: message_index ID

        Returns:
            message_index record or None
        """
        record = self._model.search([("id", "=", int(index_id))], limit=1)
        return record if record else None

    def is_local_entry(self, record: Any) -> bool:
        """
        Check if message_index is a local entry (SSOT-on-Send).

        Args:
            record: message_index record

        Returns:
            True if uid starts with 'local-'
        """
        return bool(record and record.uid and str(record.uid).startswith("local-"))

    def delete(self, record: Any) -> None:
        """
        Delete message_index record.

        Args:
            record: message_index record to delete
        """
        record.unlink()

    def delete_by_ids(self, index_ids: List[int]) -> int:
        """
        Delete multiple message_index records by IDs.

        Args:
            index_ids: List of message_index IDs

        Returns:
            Number of deleted records
        """
        records = self._model.browse(index_ids)
        count = len(records)
        records.unlink()
        return count

    def get_ssot_info(self, index_id: int) -> Optional[dict]:
        """
        Get SSOT triplet (account_id, folder, uid) by index_id.

        Args:
            index_id: message_index ID

        Returns:
            Dict with account_id, folder, uid or None
        """
        record = self.get_by_id(index_id)
        if not record:
            return None

        return {
            "account_id": record.account_id.id if record.account_id else None,
            "folder": record.folder or "",
            "uid": record.uid or "",
        }
