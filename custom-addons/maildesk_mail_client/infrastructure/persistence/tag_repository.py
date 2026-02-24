# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Tag Repository: Encapsulates tag operations on message_index SSOT.

Tags are now directly linked to message_index via Many2many relation.
Legacy mail.message.tag model has been removed.
"""

from ...domain.policies.mutation_policy import MutationPolicy


class TagRepository:
    """Repository for message tag operations via SSOT."""

    def __init__(self, env):
        self._env = env
        self._index_model = env["maildesk.message_index"].sudo()
        self._tag_model = env["mail.message.tag"].sudo()

    def get_tags_for_index_records(self, index_records):
        """
        Get tags for message_index records.

        Args:
            index_records: maildesk.message_index recordset

        Returns:
            Dict mapping index_id -> list of tag dicts
        """
        if not index_records:
            return {}

        result = {}
        for index_rec in index_records:
            if index_rec.tag_ids:
                result[index_rec.id] = [
                    {"id": t.id, "name": t.name, "color": t.color}
                    for t in index_rec.tag_ids
                ]
            else:
                result[index_rec.id] = []

        return result

    def update_tags_for_index(self, index_id, tag_ids, mutation_context=None):
        """
        Update tags for a message_index record.

        Args:
            index_id: message_index record ID
            tag_ids: List of tag IDs to set (replaces all existing)
            mutation_context: Mutation context for policy enforcement
        """
        if mutation_context:
            MutationPolicy.validate_tag_write(mutation_context)

        index_rec = self._index_model.browse(index_id)
        if index_rec.exists():
            # Odoo command: (6, 0, ids) = replace all
            index_rec.write({"tag_ids": [(6, 0, tag_ids)]})
            return True
        return False

    def get_all_tags_for_account(self, account_id):
        """
        Get all available tags for an account.

        Args:
            account_id: mailbox.account ID

        Returns:
            List of tag dicts with id, name, color
        """
        tags = self._tag_model.search([("account_id", "=", account_id)])
        return [{"id": t.id, "name": t.name, "color": t.color} for t in tags]
