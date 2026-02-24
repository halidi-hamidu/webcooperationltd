# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)

"""
ProviderDeleteAdapter: Handles provider message deletion via email_state.

Layer: infrastructure
"""

from typing import Any, List, Optional

from .move_messages_adapter import MoveMessagesAdapter
from ..persistence.email_state_repository import EmailStateRepository
from ..repositories.message_index_projection_repo import MessageIndexProjectionRepo
from ...domain.policies.mutation_policy import MutationContext, MutationIntent
from ...application.use_cases.ui_actions import DeleteMessages, DeleteMessagesParams


class ProviderDeleteAdapter:
    """
    Adapter for deleting provider messages via email_state overlay.

    Implements ProviderDeleteProtocol from delete_messages_unified.
    """

    def __init__(self, env: Any, notifier: Any = None):
        """
        Initialize adapter.

        Args:
            env: Odoo environment
            notifier: Optional bus notifier
        """
        self._env = env
        self._notifier = notifier

    def delete_provider_messages(
        self, message_ids: List[str], folder_id: Optional[int] = None
    ) -> bool:
        """
        Delete provider messages via email_state overlay.

        Args:
            message_ids: List of message IDs
            folder_id: Optional folder ID for context

        Returns:
            True on success
        """
        if not message_ids:
            return True

        state_repo = EmailStateRepository(self._env)
        mutation_context = MutationContext(
            intent=MutationIntent.UI,
            source="delete_messages",
        )

        projection_repo = MessageIndexProjectionRepo(self._env)
        deps = MoveMessagesAdapter(
            self._env, state_repo, mutation_context, projection_repo
        )
        params = DeleteMessagesParams(message_ids=message_ids, folder_id=folder_id)

        return DeleteMessages(deps, notifier=self._notifier).execute(params)
