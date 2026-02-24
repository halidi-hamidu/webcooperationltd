# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
ComposerAdapter: Infrastructure adapter for composer use cases.
Provides access to message data and helper utilities.
"""

import logging
from typing import Any, Dict, List

_logger = logging.getLogger(__name__)


class ComposerAdapter:
    """
    Adapter for PrepareReply and PrepareForward use cases.
    Implements dependency protocols for composer preparation.
    """

    def __init__(self, env):
        self.env = env

    @property
    def env(self):
        """Expose env for sanitization integration."""
        return self._env

    @env.setter
    def env(self, value):
        self._env = value

    def get_message(self, msg_key: Any) -> Dict[str, Any]:
        """
        Fetch full message data for composer (reply/forward).
        Supports both msg_key format and direct index_id.
        Robustly handles malformed keys or empty strings.
        """
        # Try parsing as triplet key first
        if isinstance(msg_key, str) and "|" in msg_key:
            parts = msg_key.split("|")
            if len(parts) >= 3:
                account_id_str, folder_id_str, uid = parts[:3]
                try:
                    param_acct_id = int(account_id_str) if account_id_str else 0
                    param_folder_id = int(folder_id_str) if folder_id_str else 0

                    params = {
                        "uid": uid,
                        "folder_id": param_folder_id,
                        "account_id": param_acct_id,
                    }

                    # IF folder is 0/missing, we might hit "SSOT index ambiguous" if multiple copies exist.
                    # We preempt this by finding *any* valid index for this (account, uid) and using it.
                    if not param_folder_id and param_acct_id and uid:
                        _logger.info(
                            f"[ComposerAdapter] Attempting to resolve ambiguous key: account={param_acct_id} uid={uid}"
                        )
                        Index = self.env["maildesk.message_index"].sudo()
                        found = Index.search(
                            [
                                ("account_id", "=", param_acct_id),
                                ("uid", "=ilike", str(uid).strip()),
                            ],
                            limit=1,
                        )
                        if found:
                            _logger.info(
                                f"[ComposerAdapter] Resolved ambiguity: using index_id={found.id} folder={found.folder}"
                            )
                            params["index_id"] = found.id
                            # Optionally set folder_id if we want to be explicit, but index_id is the strong key.
                            # params['folder_id'] = ...
                        else:
                            _logger.warning(
                                f"[ComposerAdapter] Failed to resolve key: account={param_acct_id} uid={uid} - No index found"
                            )

                    return self.env["mailbox.sync"].get_message_with_attachments(params)
                except Exception as e:
                    _logger.error(
                        f"Failed to fetch message for composer (triplet): {e}"
                    )
                    return {}

        # Try as index_id
        try:
            if not msg_key:
                return {}

            index_id = int(msg_key)
            index_rec = self.env["maildesk.message_index"].browse(index_id)
            if not index_rec.exists():
                return {}

            params = {
                "id": index_rec.id,
                "uid": index_rec.uid,
                "account_id": index_rec.account_id.id,
            }
            return self.env["mailbox.sync"].get_message_with_attachments(params)
        except Exception as e:
            _logger.error(f"Failed to fetch message for composer (index_id): {e}")
            return {}

    def get_account_email(self, account_id: int) -> str:
        """Get account email for own-email filtering."""
        try:
            account = self.env["mailbox.account"].browse(account_id)
            return (account.email or "").lower()
        except Exception:
            return ""

    def get_account_sender_name(self, account_id: int) -> str:
        """Get account sender name or fallback to name."""
        try:
            account = self.env["mailbox.account"].browse(account_id)
            return account.sender_name or account.name or ""
        except Exception:
            return ""

    def parse_email_list(self, email_str: str) -> List[str]:
        """
        Parse comma-separated email list, extract addresses.

        Args:
            email_str: "email1, Name <email2>, email3"

        Returns:
            ["email1", "email2", "email3"]
        """
        if not email_str:
            return []

        addresses = []
        for part in email_str.split(","):
            part = part.strip()
            # Extract email from "Name <email>" format
            if "<" in part and ">" in part:
                start = part.index("<") + 1
                end = part.index(">")
                addresses.append(part[start:end].strip())
            elif part:
                addresses.append(part)

        return addresses
