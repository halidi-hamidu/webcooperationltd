# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/open_message.py`.

Focus: cache hit/miss behavior and cache write contract without network access.
Layer: tests.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.open_message import OpenMessage, OpenMessageParams


class TestOpenMessage(TransactionCase):
    """Validates OpenMessage cache semantics."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()
        cls.Partner = cls.env["res.partner"].sudo()

    def _make_imap_account(self):
        server = self.FetchmailServer.create(
            {
                "name": "IMAP Server",
                "server_type": "imap",
                "server": "imap.example.com",
                "port": 993,
                "user": "imap@example.com",
                "password": "secret",
                "is_ssl": True,
            }
        )
        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            return self.Account.create(
                {
                    "name": "IMAP Account",
                    "email": "imap@example.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                }
            )

    def _make_index(self, account):
        return self.Index.create(
            {
                "account_id": account.id,
                "provider": "imap",
                "folder": "INBOX",
                "uid": "123",
                "subject": "Hello",
                "from_addr": "sender@example.com",
                "to_addrs": "imap@example.com",
                "is_read": False,
                "is_starred": False,
                "has_attachments": False,
                "flags": "",
            }
        )

    def test_cache_hit_returns_without_provider_fetch(self):
        """Cache hit must not call provider fetch and must not acquire lock."""

        account = self._make_imap_account()
        index_rec = self._make_index(account)
        partner = self.Partner.create({"name": "Sender", "email": "sender@example.com"})

        cache: Dict[int, Dict[str, Any]] = {
            index_rec.id: {
                "body_html": "<p>cached</p>",
                "body_text": "cached",
                "attachments": [],
            }
        }
        locks: list[int] = []

        class Deps:
            def index_browse(self, index_id: int):
                return self_env["maildesk.message_index"].browse(index_id)

            def index_account(self, rec):
                return rec.account_id

            def index_folder(self, rec):
                return rec.folder

            def folder_browse(self, folder_id: Optional[int]):
                return self_env["mailbox.folder"].browse(folder_id)

            def check_account_access(self, _account):
                return None

            def partner_search(self, email: str):
                return (
                    partner
                    if email == "sender@example.com"
                    else self_env["res.partner"]
                )

            def cache_read_no_lock(self, index_id: int):
                return cache.get(index_id)

            def acquire_cache_lock(self, index_id: int):
                locks.append(index_id)

            def cache_write(
                self, *, index_id: int, body_html: str, body_text: str, attachments
            ):
                raise AssertionError("cache_write must not be called on cache hit")

            def format_datetime(self, _dt):
                return "formatted"

            def avatar_html(self, _email: str, _partner):
                return "<span/>"

            def enrich_full_record_with_tags(self, _account, dto: Dict[str, Any]):
                return dto

            def enrich_partner_meta(self, dto: Dict[str, Any]):
                return dto

            def find_linked_document(
                self, _message_id: Optional[str], _in_reply_to: Optional[str]
            ) -> Tuple[Optional[str], Optional[int]]:
                return None, None

            # Normalization surface (identity for cache tests)
            def base_url(self) -> str:
                return ""

            def sanitize_email_html(self, html: str) -> str:
                return html or ""

            def strip_html_to_text(self, html: str) -> str:
                return (html or "").strip()

            def replace_cid_src(self, html: str, attachments, base_url=None) -> str:
                return html or ""

            def materialize_inline_attachments(
                self,
                *,
                provider: str,
                account,
                folder,
                uid: str,
                attachments,
                cache_key: int,
                needed_cids,
            ):
                return attachments or []

        self_env = self.env
        use_case = OpenMessage(Deps())
        use_case._open_imap_message = MagicMock(
            side_effect=AssertionError("no provider call")
        )

        result = use_case.execute(OpenMessageParams(index_id=index_rec.id, uid="123"))
        self.assertEqual(result["id"], index_rec.id)
        self.assertEqual(result["body_html"], "<p>cached</p>")
        self.assertEqual(locks, [])

    def test_cache_miss_fetches_provider_and_writes_cache(self):
        """Cache miss must fetch provider once, write cache, and update SSOT metadata."""

        account = self._make_imap_account()
        index_rec = self._make_index(account)
        partner = self.Partner.create({"name": "Sender", "email": "sender@example.com"})

        cache: Dict[int, Dict[str, Any]] = {}
        locks: list[int] = []
        writes: list[int] = []

        class Deps:
            def index_browse(self, index_id: int):
                return self_env["maildesk.message_index"].browse(index_id)

            def index_account(self, rec):
                return rec.account_id

            def index_folder(self, rec):
                return rec.folder

            def folder_browse(self, folder_id: Optional[int]):
                return self_env["mailbox.folder"].browse(folder_id)

            def check_account_access(self, _account):
                return None

            def partner_search(self, email: str):
                return (
                    partner
                    if email == "sender@example.com"
                    else self_env["res.partner"]
                )

            def cache_read_no_lock(self, index_id: int):
                return cache.get(index_id)

            def acquire_cache_lock(self, index_id: int):
                locks.append(index_id)

            def cache_write(
                self, *, index_id: int, body_html: str, body_text: str, attachments
            ):
                cache[index_id] = {
                    "body_html": body_html,
                    "body_text": body_text,
                    "attachments": attachments,
                }
                writes.append(index_id)

            def format_datetime(self, _dt):
                return "formatted"

            def avatar_html(self, _email: str, _partner):
                return "<span/>"

            def enrich_full_record_with_tags(self, _account, dto: Dict[str, Any]):
                return dto

            def enrich_partner_meta(self, dto: Dict[str, Any]):
                return dto

            def find_linked_document(
                self, _message_id: Optional[str], _in_reply_to: Optional[str]
            ) -> Tuple[Optional[str], Optional[int]]:
                return None, None

            # Normalization surface (identity for cache tests)
            def base_url(self) -> str:
                return ""

            def sanitize_email_html(self, html: str) -> str:
                return html or ""

            def strip_html_to_text(self, html: str) -> str:
                return (html or "").strip()

            def replace_cid_src(self, html: str, attachments, base_url=None) -> str:
                return html or ""

            def materialize_inline_attachments(
                self,
                *,
                provider: str,
                account,
                folder,
                uid: str,
                attachments,
                cache_key: int,
                needed_cids,
            ):
                return attachments or []

        self_env = self.env
        deps = Deps()
        use_case = OpenMessage(deps)

        provider_calls = []

        def _fake_open_imap_message(_account, _folder_name, _uid, **_kw):
            provider_calls.append((_account.id, _folder_name, _uid))
            return {
                "body_html": "<p>fetched</p>",
                "body_text": "fetched",
                "attachments": [{"id": 1, "name": "a.txt"}],
                "has_attachments": True,
            }

        use_case._open_imap_message = _fake_open_imap_message

        result = use_case.execute(OpenMessageParams(index_id=index_rec.id, uid="123"))

        self.assertEqual(len(provider_calls), 1)
        self.assertEqual(locks, [index_rec.id])
        self.assertEqual(writes, [index_rec.id])
        self.assertEqual(result["body_html"], "<p>fetched</p>")
        self.assertTrue(result["has_attachments"])

        index_rec.invalidate_recordset()
        self.assertTrue(index_rec.has_attachments)

    def test_gmail_fetch_provider_payload_accepts_message_id_kwarg(self):
        """
        Regression: `_fetch_provider_payload()` passes `message_id=` to the Gmail open path.
        `_open_gmail_message()` must accept it (even if unused) to avoid runtime TypeError.
        """
        account = self._make_imap_account()
        index_rec = self.Index.create(
            {
                "account_id": account.id,
                "provider": "gmail",
                "folder": "INBOX",
                "uid": "19bce48103c6ffe5",
                "message_id": "<m@example.com>",
                "subject": "Hello",
                "from_addr": "sender@example.com",
                "to_addrs": "imap@example.com",
                "is_read": False,
                "is_starred": False,
                "has_attachments": False,
                "flags": "",
            }
        )

        self_env = self.env
        calls = []

        class Deps:
            def gmail_build_service(self, _account):
                return object()

            def gmail_get_message_full(self, _service, _account, _folder, uid: str):
                calls.append(uid)
                return {
                    "body_html": "<p>gmail</p>",
                    "body_text": "gmail",
                    "attachments": [],
                    "has_attachments": False,
                    "message_id": "<m@example.com>",
                }

            def enrich_partner_meta(self, dto: Dict[str, Any]):
                return dto

            def find_linked_document(
                self, _message_id: Optional[str], _in_reply_to: Optional[str]
            ) -> Tuple[Optional[str], Optional[int]]:
                return None, None

            def enrich_full_record_with_tags(self, _account, dto: Dict[str, Any]):
                return dto

            @property
            def env(self):
                return self_env

            def partner_search(self, email: str):
                return self.env["res.partner"]

            def avatar_html(self, _email: str, _partner):
                return "<span/>"

        payload = OpenMessage(Deps())._fetch_provider_payload(
            index_rec=index_rec, account=account, folder=None
        )

        self.assertEqual(calls, [index_rec.uid])
        self.assertEqual(payload["body_html"], "<p>gmail</p>")
