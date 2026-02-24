# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Message Meta Bulk Adapter.

Implements infrastructure integration for Message Meta Bulk Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from typing import Any, Sequence

from ..providers.gmail import gmail_fetch_meta_batch
from ..providers.gmail.auth import gmail_build_service, is_gmail_account
from ..providers.imap import fetch_list_records_parallel
from ..providers.outlook import outlook_fetch_meta_batch
from ..providers.outlook.client_factory import (
    get_outlook_client,
    is_outlook_account,
)


class MessageMetaBulkAdapter:
    """
    Adapter for fetching message metadata in bulk across different providers.

    Implements provider routing and delegates to Gmail API, Outlook Graph,
    or IMAP parallel fetching based on account type.
    """

    def __init__(self, env):
        self.env = env

    def fetch_bulk(
        self, account_id: int, folder_id: int, uids: Sequence[Any]
    ) -> list[dict]:
        """
        Fetch lightweight metadata for a batch of message UIDs.

        Args:
            account_id: ID of the mailbox account
            folder_id: ID of the folder containing the messages
            uids: List of message UIDs to fetch

        Returns:
            List of message metadata dictionaries
        """
        Account = self.env["mailbox.account"].browse(account_id)
        Folder = self.env["mailbox.folder"].browse(folder_id)

        if not Account or not Folder or not uids:
            return []

        partner_cache = {}

        # Gmail provider
        if is_gmail_account(Account):
            service = gmail_build_service(Account)
            return gmail_fetch_meta_batch(
                self.env,
                self.env["mailbox.sync"],  # Pass sync model for compatibility
                service,
                Account,
                Folder,
                [str(u) for u in uids],
                partner_cache,
            )

        # Outlook provider
        if is_outlook_account(Account):
            sess, base = get_outlook_client(self.env, Account)
            if sess and base:
                return outlook_fetch_meta_batch(
                    self.env,
                    self.env["mailbox.sync"],
                    sess,
                    base,
                    Account,
                    Folder,
                    [str(u) for u in uids],
                    partner_cache,
                )

        # IMAP provider (fallback)
        return fetch_list_records_parallel(
            self.env,
            client=False,
            uids=[int(u) for u in uids],
            folder=Folder,
            account=Account,
            partner_cache=partner_cache,
        )
