# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Threading.

Defines domain concepts used by MailDesk (Threading).
Layer: domain.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..contracts.threading_contract import ThreadingServiceDeps


@dataclass(frozen=True)
class ThreadingParams:
    """Parameters for fetching a thread."""

    account: Any
    message_id: str  # The Message-ID header value to start from
    folder_name: Optional[str] = None  # For IMAP: which folder to search
    thread_id: Optional[str] = None  # For Gmail: the threadId
    include_bodies: bool = True  # Whether to fetch full bodies


class ThreadingService:
    """
    Domain service for fetching and building message threads.
    Centralizes threading logic shared by all providers.
    """

    def __init__(self, deps: ThreadingServiceDeps):
        self._deps = deps

    def execute(self, params: ThreadingParams) -> List[Dict[str, Any]]:
        """
        Fetch a thread and return the chain of messages.
        delegates to provider-specific logic based on account type.
        """
        # Deterministic rule:
        # - If `thread_id` is provided, always use SSOT topology and hydrate via OpenMessage (cache-read / fetch / cache-write).
        # - Only if `thread_id` is missing do we fall back to provider-specific strategies.
        if params.thread_id:
            return self._fetch_thread_from_ssot(params)
        if self._deps.is_gmail_account(params.account):
            return self._fetch_gmail_thread(params)
        return self._fetch_thread_from_ssot(params)

    def _fetch_gmail_thread(self, params: ThreadingParams) -> List[Dict[str, Any]]:
        """
        Fetch Gmail thread using the API.
        """
        if not params.thread_id:
            return []

        service = self._deps.gmail_build_service(params.account)
        chain = self._deps.gmail_get_thread_full(
            service, params.account, params.thread_id, params.include_bodies
        )
        return chain or []

    def _fetch_outlook_thread(self, params: ThreadingParams) -> List[Dict[str, Any]]:
        return self._fetch_thread_from_ssot(params)

    def _fetch_imap_thread(self, params: ThreadingParams) -> List[Dict[str, Any]]:
        return self._fetch_thread_from_ssot(params)

    def _fetch_thread_from_ssot(self, params: ThreadingParams) -> List[Dict[str, Any]]:
        """
        Fetch thread topology from SSOT (DB) and hydrate with full content.

        This strategy is superior to recursive provider fetching because:
        1. It finds ALL messages in the thread (ancestors AND descendants) using the shared thread_id.
        2. It avoids expensive recursive IMAP SEARCH calls.
        3. It robustly handles bodies by hydrating via get_message_with_attachments.
        """
        if not params.thread_id:
            return self._build_ancestor_chain_from_index(params)

        # 1. Get topology from DB (fast, includes all folders)
        # Note: 'include_bodies' in this call only affects what the adapter *tries* to get from DB,
        # but the adapter currently returns summaries. We will ignore its body fields and hydrate manually.
        summary_list = self._deps.get_thread_messages_from_db(
            params.account, params.thread_id, include_bodies=False
        )

        if not summary_list:
            # Fallback: Use recursive in_reply_to lookup from message_index (legacy callers).
            return self._build_ancestor_chain_from_index(params)

        # Hydrate every thread message using OpenMessage (cache-first, provider-fetch on miss, cache persist).
        acc_id = params.account.id
        chain: List[Dict[str, Any]] = []
        for item in summary_list:
            full = self._deps.get_message_with_attachments(
                {
                    "id": item.get("id"),
                    "uid": item.get("uid"),
                    "folder_id": item.get("folder_id"),
                    "account_id": acc_id,
                }
            )
            if not full:
                raise RuntimeError(
                    "Thread hydration failed for "
                    f"account_id={acc_id} index_id={item.get('id')} folder_id={item.get('folder_id')} uid={item.get('uid')!r}"
                )
            chain.append(full)

        return chain

    def _build_ancestor_chain_from_index(
        self, params: ThreadingParams
    ) -> List[Dict[str, Any]]:
        """
        Build ancestor chain by recursively following in_reply_to links in message_index.

        This is a fallback when thread_id is not available (IMAP/Outlook).
        Starting from the current message's in_reply_to, we walk backwards through
        the chain until we reach the root of the conversation.

        Returns:
            List of hydrated ancestor messages (oldest first)
        """
        if not params.message_id:
            return []

        chain = []
        visited = set()

        # Start by finding the current message to get its in_reply_to
        current_msg = self._deps.find_message_by_message_id(
            params.account, params.message_id
        )

        if not current_msg:
            return []

        current_in_reply_to = current_msg.get("in_reply_to")

        # Walk backwards through the chain
        while current_in_reply_to and current_in_reply_to not in visited:
            visited.add(current_in_reply_to)

            # Search for message with message_id matching current_in_reply_to
            parent_msg = self._deps.find_message_by_message_id(
                params.account, current_in_reply_to
            )

            if not parent_msg:
                break

            # Hydrate full message
            full = self._deps.get_message_with_attachments(
                {
                    "uid": parent_msg.get("uid"),
                    "folder_id": parent_msg.get("folder_id"),
                    "account_id": params.account.id,
                }
            )

            if full:
                # Prepend to chain (we're walking backwards, want oldest first)
                chain.insert(0, full)

                # Continue with parent's in_reply_to
                current_in_reply_to = parent_msg.get("in_reply_to")
            else:
                break

        return chain

    def _build_thread_lazy(
        self,
        account: Any,
        folder_name: str,
        msg_id: str,
        checked_folders: set,
        chain: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Recursively build thread chain for IMAP accounts.
        """
        if not msg_id:
            return chain

        pool = self._deps.get_pool(account)

        # Try to find message in current folder
        with pool.session() as client:
            try:
                client.select_folder(folder_name, readonly=True)
                needle = (msg_id or "").strip()
                if needle and not (needle.startswith("<") and needle.endswith(">")):
                    needle = f"<{needle}>"
                uids = client.search(["HEADER", "Message-ID", needle]) or []
            except Exception:
                uids = []

            if uids:
                uid = uids[0]

                # Find folder record
                folder_rec = self._deps.folder_search(
                    [
                        ("account_id", "=", self._deps.account_id(account)),
                        "|",
                        ("imap_name", "=", folder_name),
                        ("name", "=", folder_name),
                    ],
                    limit=1,
                )

                # Fetch full message
                full = self._deps.get_message_with_attachments(
                    {
                        "uid": uid,
                        "folder_id": self._deps.folder_id(folder_rec)
                        if folder_rec
                        else False,
                        "account_id": self._deps.account_id(account),
                    }
                )

                if full:
                    # Keep thread metadata in-memory for this response
                    self._deps.cache_upsert_meta(
                        account_id=self._deps.account_id(account),
                        folder=folder_name,
                        uid=uid,
                        vals={
                            "subject": full.get("subject"),
                            "from_addr": full.get("email_from"),
                            "date": full.get("date"),
                            "to_addrs": full.get("to_display"),
                            "cc_addrs": full.get("cc_display"),
                            "bcc_addrs": full.get("bcc_display"),
                            "has_attachments": full.get("has_attachments"),
                            "body_html": full.get("body_original"),
                            "body_text": full.get("body_plain"),
                            "message_id": full.get("message_id"),
                            "sender_display_name": full.get("sender_display_name"),
                            "avatar_html": full.get("avatar_html"),
                        },
                        ttl_minutes=60,
                    )

                    chain.append(full)
                    next_id = full.get("in_reply_to") or ""
                    if next_id:
                        return self._build_thread_lazy(
                            account, folder_name, next_id, checked_folders, chain
                        )
                    return chain

        # If not found in current folder, search in top folders
        TOP_FOLDERS = [
            "INBOX",
            "Sent",
            "Gesendet",
            "Gesendete Objekte",
            "Archive",
            "Archives",
            "Drafts",
            "Entwürfe",
            "Trash",
            "Gelöscht",
            "Gelöschte Objekte",
            "Papierkorb",
        ]
        if folder_name not in TOP_FOLDERS:
            TOP_FOLDERS.insert(0, folder_name)

        folders = self._deps.folder_search(
            [
                ("account_id", "=", self._deps.account_id(account)),
                ("imap_name", "in", TOP_FOLDERS),
            ],
            limit=len(TOP_FOLDERS),
        )

        for f in folders:
            f_name = self._deps.folder_imap_name(f)
            if f_name in checked_folders:
                continue
            checked_folders.add(f_name)

            with pool.session() as client:
                try:
                    client.select_folder(f_name, readonly=True)
                    needle = (msg_id or "").strip()
                    if needle and not (needle.startswith("<") and needle.endswith(">")):
                        needle = f"<{needle}>"
                    uids = client.search(["HEADER", "Message-ID", needle]) or []
                except Exception:
                    uids = []

            if not uids:
                continue

            uid = uids[0]
            full = self._deps.get_message_with_attachments(
                {
                    "uid": uid,
                    "folder_id": self._deps.folder_id(f),
                    "account_id": self._deps.account_id(account),
                }
            )

            if not full:
                continue

            # Keep thread metadata in-memory for this response
            self._deps.cache_upsert_meta(
                account_id=self._deps.account_id(account),
                folder=f_name,
                uid=uid,
                vals={
                    "subject": full.get("subject"),
                    "from_addr": full.get("email_from"),
                    "date": full.get("date"),
                    "to_addrs": full.get("to_display"),
                    "cc_addrs": full.get("cc_display"),
                    "bcc_addrs": full.get("bcc_display"),
                    "has_attachments": full.get("has_attachments"),
                    "body_html": full.get("body_original"),
                    "body_text": full.get("body_plain"),
                    "message_id": full.get("message_id"),
                    "sender_display_name": full.get("sender_display_name"),
                    "avatar_html": full.get("avatar_html"),
                },
                ttl_minutes=60,
            )

            chain.append(full)
            next_id = full.get("in_reply_to") or ""
            if next_id:
                return self._build_thread_lazy(
                    account, f_name, next_id, checked_folders, chain
                )

        return chain
