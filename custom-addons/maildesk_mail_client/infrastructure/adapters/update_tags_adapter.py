# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
UpdateTags Adapter: Implements deps protocol for UpdateTags use-case.

Clean Architecture compliant:
- Injects MessageIndexProjectionRepo for SSOT tag operations
- No legacy tag.link operations
"""


class UpdateTagsAdapter:
    """
    Adapter for UpdateTags use case.

    Clean Architecture:
    - Injects projection_repo for message_index operations
    - Tags are now directly in SSOT via Many2many
    """

    def __init__(self, env, tag_repo, mutation_context, projection_repo):
        """
        Args:
            env: Odoo environment
            tag_repo: Tag repository (for SSOT tag operations)
            mutation_context: Mutation tracking context
            projection_repo: MessageIndexProjectionRepo (for CQRS projection)
        """
        self.env = env
        self._tag_repo = tag_repo
        self._mutation_context = mutation_context
        self._projection_repo = projection_repo

    def tag_get_all_for_account(self, account_id):
        """Get all tags for an account."""
        return self._tag_repo.get_all_tags_for_account(account_id)

    def index_update_tags(self, account_id, folder, uid, tag_ids):
        """
        CQRS projection: Update message_index denormalized tags.

        Clean Architecture: Delegates to repository.
        """
        return self._projection_repo.update_tags(account_id, folder, uid, tag_ids)

    def get_msg_ssot_info(self, index_id):
        """Get SSOT triplet info by message_index ID."""
        Index = self.env["maildesk.message_index"]
        rec = Index.browse(index_id).exists()
        if not rec:
            return None
        return {
            "account_id": rec.account_id.id,
            "folder": rec.folder,
            "uid": rec.uid,
            "message_id": rec.message_id,
        }
