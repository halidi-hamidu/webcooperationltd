# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Threading Contract.

Defines domain concepts used by MailDesk (Threading Contract).
Layer: domain.
"""

from typing import Any, Dict, List, Protocol


class ThreadingServiceDeps(Protocol):
    """
    Dependency contract required by the ThreadingService.
    Pure domain protocol, no Odoo dependencies allowed.
    """

    # Environment / models
    def cache_search(self, domain: List[Any], limit: int) -> Any: ...
    def cache_upsert_meta(
        self,
        account_id: int,
        folder: str,
        uid: Any,
        vals: Dict[str, Any],
        ttl_minutes: int,
    ) -> Any: ...
    def folder_search(self, domain: List[Any], limit: int) -> Any: ...
    def folder_imap_name(self, folder: Any) -> str: ...
    def folder_id(self, folder: Any) -> int: ...

    # Account info
    def account_id(self, account: Any) -> int: ...
    def is_gmail_account(self, account: Any) -> bool: ...

    # Gmail thread fetching
    def gmail_build_service(self, account: Any) -> Any: ...
    def gmail_get_thread_full(
        self, service: Any, account: Any, thread_id: str, include_bodies: bool
    ) -> List[Dict[str, Any]]: ...

    # IMAP thread fetching
    def get_pool(self, account: Any) -> Any: ...
    def get_message_with_attachments(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]: ...

    # Message lookup from message_index
    def find_message_by_message_id(
        self, account: Any, message_id: str
    ) -> Dict[str, Any]: ...

    def get_thread_messages_from_db(
        self, account: Any, thread_id: str, include_bodies: bool
    ) -> List[Dict[str, Any]]: ...

    def is_outlook_account(self, account: Any) -> bool: ...

    # Helpers
    def norm_msgid(self, msgid: str) -> str: ...
