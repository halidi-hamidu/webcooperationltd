# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
SaveDraft Use-Case: Handles draft creation and updating.
Encapsulates draft business logic in application layer.
"""

from dataclasses import dataclass
from typing import List, Optional

from ..services.normalize_outgoing_html import NormalizeOutgoingHtml


@dataclass(frozen=True)
class SaveDraftParams:
    """Parameters for saving a draft."""

    account_id: int
    draft_id: Optional[int] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    to: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    attachment_ids: Optional[List[int]] = None
    request_read_receipt: bool = False
    request_delivery_receipt: bool = False
    sender_display_name: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    reply_to_cache_uid: Optional[str] = None
    model: Optional[str] = None
    res_id: Optional[int] = None


class SaveDraft:
    """
    Use-case: Save or update a draft.

    Handles both creating new drafts and updating existing ones.
    All ORM access delegated to DraftRepository.

    CRITICAL: Normalizes outgoing HTML before save to enforce CID invariants.
    This ensures all cid: references use stable Content-IDs and map to real attachments.
    """

    def __init__(self, draft_repo, text_helper, env):
        """
        Initialize SaveDraft use-case.

        Args:
            draft_repo: DraftRepository instance
            text_helper: Helper for list <-> text conversion
            env: Odoo environment for accessing attachments
        """
        self._draft_repo = draft_repo
        self._text_helper = text_helper
        self._env = env

    def execute(self, params: SaveDraftParams) -> int:
        """
        Execute draft save.

        Args:
            params: SaveDraftParams

        Returns:
            Draft ID (int)
        """
        # Check if updating existing draft
        draft = None
        if params.draft_id:
            draft = self._draft_repo.browse(params.draft_id)
            if not self._draft_repo.exists(draft):
                draft = None

        # NORMALIZE OUTGOING HTML before save
        # This ensures all cid: references use stable Content-IDs
        # and all referenced attachments have content_id field set.
        normalizer = NormalizeOutgoingHtml(self._env)
        body_html_normalized, _ = normalizer.normalize(
            params.body_html or "", params.attachment_ids or []
        )

        # Build draft values
        vals = {
            "account_id": params.account_id,
            "subject": params.subject or "",
            "body_html": body_html_normalized,  # NORMALIZED (not raw)
            "to_emails": self._text_helper.to_text(params.to or []),
            "cc_emails": self._text_helper.to_text(params.cc or []),
            "bcc_emails": self._text_helper.to_text(params.bcc or []),
            "request_read_receipt": params.request_read_receipt,
            "request_delivery_receipt": params.request_delivery_receipt,
            "sender_display_name": params.sender_display_name or "",
            "reply_to_message_id": params.reply_to_message_id,
            "reply_to_cache_uid": params.reply_to_cache_uid,
            "model": params.model,
            "res_id": params.res_id or False,
        }

        # Handle attachments
        att_ids = [a for a in (params.attachment_ids or []) if a]
        vals["attachment_ids"] = [(6, 0, att_ids)] if att_ids else [(5, 0, 0)]

        # Create or update
        if draft:
            self._draft_repo.update(draft, vals)
            return draft.id
        else:
            new_draft = self._draft_repo.create(vals)
            return new_draft.id
