# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Domain Mutation Policy

Formalizes and enforces mutation rules for MailDesk 3.0.

This module centralizes all rules about who can write what, making implicit
conventions (e.g., "Gmail is read-only", "UI never touches providers") explicit
and enforceable in code.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MutationIntent(Enum):
    """
    Declares the intent behind a state mutation.

    This makes explicit WHERE a write is coming from, enabling policy enforcement.
    """

    UI = "ui"  # User-triggered action (set flags, move, delete, tags)
    SYNC = "sync"  # Background synchronization with provider
    PROVIDER = "provider"  # Direct provider operation (rare)


@dataclass(frozen=True)
class MutationContext:
    """
    Context for a state mutation.

    Every write operation must declare its intent and source for policy validation.
    """

    intent: MutationIntent
    source: str  # e.g., "set_flags", "sync_folder", "imap_sync"
    account_id: Optional[int] = None
    provider_type: Optional[str] = None  # "gmail", "outlook", "imap"
    context_data: Optional[dict] = None


class MutationPolicyViolation(Exception):
    """Raised when a mutation violates the domain policy."""

    pass


class MutationPolicy:
    """
    Centralized mutation rules for MailDesk 3.0.

    Rules:
    1. UI-triggered actions (flags, tags, move, delete) write ONLY to:
       - maildesk.email_state (pending operations queue)
       - maildesk.message_index (SSOT projections including tags)
    2. UI-triggered actions NEVER write to providers (Gmail/Outlook/IMAP)
    3. Background sync is the ONLY path that writes to providers
    4. Gmail and Outlook are read-only even from sync (state overlay only)
    5. Only IMAP supports bidirectional sync
    """

    @staticmethod
    def validate_email_state_write(context: MutationContext) -> None:
        """
        Validate that writing to maildesk.email_state is allowed.

        Rules:
        - UI intent: ALLOWED (state overlay)
        - SYNC intent: ALLOWED (sync reconciliation)
        - PROVIDER intent: NOT ALLOWED
        """
        if context.intent == MutationIntent.PROVIDER:
            raise MutationPolicyViolation(
                f"PROVIDER intent cannot write to email_state. Source: {context.source}"
            )

    @staticmethod
    def validate_tag_write(context: MutationContext) -> None:
        """
        Validate that writing tags to message_index is allowed.

        Rules:
        - UI intent: ALLOWED (tags are local-only, stored in SSOT)
        - SYNC intent: NOT ALLOWED (tags don't sync to providers)
        - PROVIDER intent: NOT ALLOWED
        """
        if context.intent != MutationIntent.UI:
            raise MutationPolicyViolation(
                f"Only UI intent can write tags. "
                f"Got: {context.intent}, source: {context.source}"
            )

    @staticmethod
    def validate_provider_write(context: MutationContext) -> None:
        """
        Validate that writing to provider (Gmail/Outlook/IMAP) is allowed.

        Rules:
        - UI intent: NOT ALLOWED (UI writes go to email_state only)
        - SYNC intent: ALLOWED for IMAP only
        - Gmail/Outlook: READ-ONLY (use state overlay)
        """
        if context.intent == MutationIntent.UI:
            raise MutationPolicyViolation(
                f"UI intent cannot write to providers. "
                f"Use email_state for overlays. Source: {context.source}"
            )

        if context.provider_type in ["gmail", "outlook"]:
            raise MutationPolicyViolation(
                f"{context.provider_type} is read-only. "
                f"Use email_state for overlays. Source: {context.source}"
            )

    @staticmethod
    def validate_cache_write(context: MutationContext) -> None:
        """
        Validate that writing to message cache is allowed.

        Rules:
        - All intents ALLOWED (cache is ephemeral storage)
        """
        # Cache writes are always allowed - it's just ephemeral storage
        pass
