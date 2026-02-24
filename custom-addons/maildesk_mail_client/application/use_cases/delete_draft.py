# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
DeleteDraft Use-Case: Deletes a draft.
Simple delegation to repository.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeleteDraftParams:
    """Parameters for deleting a draft."""

    draft_id: int


class DeleteDraft:
    """
    Use-case: Delete a draft.

    Simple delegation to repository.
    """

    def __init__(self, draft_repo):
        """
        Initialize DeleteDraft use-case.

        Args:
            draft_repo: DraftRepository instance
        """
        self._draft_repo = draft_repo

    def execute(self, params: DeleteDraftParams) -> bool:
        """
        Execute draft deletion.

        Args:
            params: DeleteDraftParams

        Returns:
            True if deleted, False if not found
        """
        draft = self._draft_repo.browse(params.draft_id)
        if self._draft_repo.exists(draft):
            self._draft_repo.delete(draft)
            return True
        return False
