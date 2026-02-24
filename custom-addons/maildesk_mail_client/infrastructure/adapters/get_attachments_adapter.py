# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Get Attachments Adapter.

Implements infrastructure integration for Get Attachments Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from ...application.use_cases.open_message import OpenMessage, OpenMessageParams
from .open_message_adapter import OpenMessageAdapter


class GetAttachmentsAdapter:
    """
    Adapter for fetching message attachments via provider.

    Fetches full message from provider and creates ir.attachment records
    for binary delivery.
    """

    def __init__(self, env):
        self.env = env

    def get_attachments(self, account_id: int, folder: str, uid: str) -> list[dict]:
        """
        Return attachment descriptors for a cached message.

        Args:
            account_id: ID of the mailbox account
            folder: Folder name (IMAP name or display name)
            uid: Message UID

        Returns:
            List of attachment dictionaries with URLs for download
        """
        folder_rec = self.env["mailbox.folder"].search(
            [
                ("account_id", "=", int(account_id)),
                "|",
                ("imap_name", "=", folder),
                ("name", "=", folder),
            ],
            limit=1,
        )

        deps = OpenMessageAdapter(self.env)
        open_params = OpenMessageParams(
            uid=str(uid),
            folder_id=int(folder_rec.id) if folder_rec else False,
            account_id=int(account_id),
            is_internal_draft=False,
        )
        full = OpenMessage(deps).execute(open_params) or {}

        # Canonical: attachments are returned as ir.attachment descriptors (id + token),
        # served via standard Odoo routes.
        return full.get("attachments") or []
