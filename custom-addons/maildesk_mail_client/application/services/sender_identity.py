# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Sender Identity Service

CANONICAL SOURCE OF TRUTH for resolving the visual sender identity of a message.

Contract:
- Inputs: Message Headers (from/to), Folder Context (record or name).
- Output: Standardized SenderIdentity dict.

This service eliminates inconsistency between List, Detail, and Thread views
by providing a single algorithm for projecting "Technical Sender" to "Visual Identity".
"""

from typing import Any, Dict, Protocol

# Re-use existing formatting logic but encapsulate it here
from .display_formatting import (
    compute_display_contact,
    format_sender_display,
)


class SenderIdentityDeps(Protocol):
    """Dependencies for Sender Identity resolution."""

    def partner_search(self, email: str) -> Any: ...
    def avatar_html(self, email: str, partner: Any) -> str: ...
    def folder_type(self, folder: Any) -> str: ...


class SenderIdentityService:
    def __init__(self, deps: SenderIdentityDeps):
        self._deps = deps

    def resolve_visual_identity(
        self,
        *,
        from_addr: str,
        to_addrs: str,
        sender_display_name_header: str,
        folder: Any = None,
        folder_name_heuristic: str = None,
    ) -> Dict[str, Any]:
        """
        Compute the canonical visual identity for a message.

        Args:
            from_addr: Technical sender email (SMTP From)
            to_addrs: Technical recipients (SMTP To)
            sender_display_name_header: Name from headers (or SSOT)
            folder: Optional mailbox.folder record
            folder_name_heuristic: Optional folder name string (from index)

        Returns:
            Dict containing:
            - visual_email: The email address to display
            - sender_display_name: The name to display
            - avatar_partner_id: ID of the partner representing the visual sender
            - avatar_html: HTML for the avatar
            - partner_trusted: Boolean trust status
            - content_trusted: Boolean trust status for rendering HTML content
            - folder_type: The resolved folder context used
        """
        # 1. Resolve Context (Folder Type)
        folder_type = self._resolve_folder_type(folder, folder_name_heuristic)

        # 2. Compute Visual Contact (Sender vs Recipient)
        # Note: compute_display_contact handles the "Sent = Recipient" logic
        display_email, raw_display_name = compute_display_contact(
            folder_type=folder_type,
            from_addr=from_addr or "",
            to_addrs=to_addrs or "",
            sender_display_name=sender_display_name_header or from_addr or "",
        )

        # 3. Resolve Partner (for Avatar and Trust)
        partner = self._deps.partner_search(display_email)

        # 4. Finalize Display Name (Enrich with Partner Name)
        final_display_name = raw_display_name
        if partner and partner.display_name:
            final_display_name = partner.display_name

        # Ensure "Name <email>" format consistency
        final_display_name = format_sender_display(final_display_name, display_email)

        partner_trusted = bool(partner.trusted_partner) if partner else False
        content_trusted = folder_type in {"sent", "drafts"} or partner_trusted

        return {
            "visual_email": display_email,
            "sender_display_name": final_display_name,
            "avatar_partner_id": partner.id if partner else False,
            "avatar_html": self._deps.avatar_html(display_email, partner),
            "partner_trusted": partner_trusted,
            "content_trusted": content_trusted,
            "trusted_by_user_id": (
                partner.trusted_by_user_id.id
                if partner
                and hasattr(partner, "trusted_by_user_id")
                and partner.trusted_by_user_id
                else False
            ),
            "folder_type": folder_type,
        }

    def _resolve_folder_type(self, folder: Any, folder_name_heuristic: str) -> str:
        """
        Robustly determine folder type.
        Priority:
        1. mailbox.folder record .folder_type (if known/valid)
        2. folder_name_heuristic string (e.g. "Sent", "Outbox")
        3. Default "other" (Inbox behavior)
        """
        # 1. Check Record
        type_from_record = self._deps.folder_type(folder) if folder else None
        if type_from_record and type_from_record != "other":
            return type_from_record

        # 2. Check Heuristic (Fallback for missing folders or generic types)
        if folder_name_heuristic:
            fname = folder_name_heuristic.lower()
            if "sent" in fname or fname == "outbox":
                return "sent"
            if "draft" in fname:
                return "drafts"
            if "trash" in fname or "bin" in fname:
                return "trash"
            if "junk" in fname or "spam" in fname:
                return "junk"
            if "archive" in fname:
                return "archive"

        # 3. Default
        return "other"
