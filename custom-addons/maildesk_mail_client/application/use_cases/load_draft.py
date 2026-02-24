# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
LoadDraft Use-Case: Retrieves draft data for editing.
Returns structured dict,not ORM records.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadDraftParams:
    """Parameters for loading a draft."""

    draft_id: int


class LoadDraft:
    """
    Use-case: Load a draft for editing.

    Returns structured data suitable for UI, not ORM records.
    """

    def __init__(self, draft_repo, text_helper):
        """
        Initialize LoadDraft use-case.

        Args:
            draft_repo: DraftRepository instance
            text_helper: Helper for text <-> list conversion
        """
        self._draft_repo = draft_repo
        self._text_helper = text_helper

    def execute(self, params: LoadDraftParams) -> dict:
        """
        Execute draft load.

        Args:
            params: LoadDraftParams

        Returns:
            Dict with draft data

        Raises:
            ValueError: If draft not found
        """
        draft = self._draft_repo.browse(params.draft_id)
        if not self._draft_repo.exists(draft):
            raise ValueError(f"Draft {params.draft_id} not found")

        account = draft.account_id

        # Convert email lists
        to_list = self._text_helper.to_list(draft.to_emails)
        cc_list = self._text_helper.to_list(draft.cc_emails)
        bcc_list = self._text_helper.to_list(draft.bcc_emails)

        # Build attachments list
        attachments = [
            {
                "id": att.id,
                "name": att.name,
                "mimetype": att.mimetype,
            }
            for att in draft.attachment_ids
        ]

        tag_ids = [
            {"id": t.id, "name": t.name, "color": t.color} for t in draft.tag_ids
        ]

        return {
            "id": draft.id,
            "account_id": account.id,
            "subject": draft.subject or "",
            "body_html": draft.body_html or "",
            "to": to_list,
            "cc": cc_list,
            "bcc": bcc_list,
            "attachments": attachments,
            "tag_ids": tag_ids,
            "reply_to_msg": draft.reply_to_cache_uid or None,
            "request_read_receipt": bool(draft.request_read_receipt),
            "request_delivery_receipt": bool(draft.request_delivery_receipt),
            "from_display": draft.sender_display_name
            or account.sender_name
            or account.name
            or (account.email or ""),
            "model": draft.model or None,
            "res_id": draft.res_id or None,
            "message_id": draft.reply_to_message_id or "",
        }
