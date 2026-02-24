# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Unread Counts Adapter.

Implements infrastructure integration for Unread Counts Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

import logging
from typing import Optional

_logger = logging.getLogger(__name__)


class UnreadCountsAdapter:
    """
    Adapter for calculating unread message counts using purely local SSOT.
    Simplified as per user request to rely solely on maildesk.message_index.
    """

    def __init__(self, env):
        self.env = env

    def get_counts(
        self,
        account_id: int,
        folder_id: int,
        flt: Optional[str] = None,
        text: Optional[str] = None,
        partner_id: Optional[int] = None,
        email_from: Optional[str] = None,
    ) -> dict:
        """
        Calculate unread message counts for a folder using SSOT (maildesk.message_index).
        """
        Index = self.env["maildesk.message_index"]
        Folder = self.env["mailbox.folder"].browse(folder_id)

        if not Folder.exists():
            return {"unread_total": 0, "unread_filtered": 0}

        # Base domain for TOTAL unread in folder
        base_domain = [
            ("account_id", "=", account_id),
            ("folder", "=", Folder.imap_name),
            ("is_read", "=", False),
        ]

        unread_total = Index.search_count(base_domain)

        # If no filters, filtered count == total count
        if not any([flt, text, partner_id, email_from]) or flt == "all":
            return {"unread_total": unread_total, "unread_filtered": unread_total}

        # Build domain for FILTERED unread
        filtered_domain = list(base_domain)

        if flt == "starred":
            filtered_domain.append(("is_starred", "=", True))

        if text:
            # Simple text search on subject/from
            filtered_domain.append("|")
            filtered_domain.append(("subject", "ilike", text))
            filtered_domain.append(("from_addr", "ilike", text))

        if email_from:
            filtered_domain.append(("from_addr", "ilike", email_from))

        # Note: partner_id filtering on message_index might require joins if index doesn't have partner_id
        # For now, we ignore partner_id in unread count or assume frontend passes email_from

        unread_filtered = Index.search_count(filtered_domain)

        return {
            "unread_total": unread_total,
            "unread_filtered": unread_filtered,
        }

    def get_partner_unread_distribution(
        self, account_id: int, partner_email: str
    ) -> dict:
        """
        Get unread counts grouped by folder for a specific partner.

        Logic:
           - Filter by account_id
           - Filter by is_read=False
           - Filter by participation (From OR To OR Cc OR Bcc ILIKE partner_email)
           - Group by 'folder' field (which is the char name in message_index)
           - Map folder names back to folder IDs using mailbox.folder search

        Return dict(folder_id,unread_count)
        """
        if not partner_email:
            return {}

        domain = [
            ("account_id", "=", int(account_id)),
            ("is_read", "=", False),
            ("deleted_on_server", "!=", True),
            ("pending_delete", "!=", True),
            "|",
            "|",
            "|",
            ("from_addr", "ilike", partner_email),
            ("to_addrs", "ilike", partner_email),
            ("cc_addrs", "ilike", partner_email),
            ("bcc_addrs", "ilike", partner_email),
        ]

        MessageIndex = self.env["maildesk.message_index"]
        groups = MessageIndex.read_group(domain, fields=["folder"], groupby=["folder"])
        # Result format: [{'folder': 'INBOX', 'folder_count': 5}, ...]

        # Map folder names to counts
        folder_counts_by_name = {}
        for g in groups:
            folder_name = g.get("folder")
            count = g.get("id:count")
            if folder_name and count:
                folder_counts_by_name[folder_name] = count

        if not folder_counts_by_name:
            return {}

        # Resolve Folder IDs for this account
        folder_names = list(folder_counts_by_name.keys())
        folders = self.env["mailbox.folder"].search(
            [("account_id", "=", int(account_id)), ("imap_name", "in", folder_names)]
        )

        # Build strict {id: count} map
        result = {}
        for folder in folders:
            # Match by imap_name (which corresponds to 'folder' in index)
            count = folder_counts_by_name.get(folder.imap_name)
            if count:
                result[folder.id] = count

        return result
