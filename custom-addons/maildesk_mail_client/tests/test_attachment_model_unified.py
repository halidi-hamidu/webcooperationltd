# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Attachment model refactor regression tests.

Goal: ensure MailDesk never relies on legacy custom attachment endpoints and
always returns ir.attachment-backed descriptors for Gmail/Outlook attachments.
"""

from __future__ import annotations

import base64
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..application.services.attachment_cache_service import (
    AttachmentCacheService,
    AttachmentMaterializeRequest,
    AttachmentSource,
)
from ..infrastructure.adapters.open_message_adapter import OpenMessageAdapter
from ..infrastructure.repositories.attachment_repository import AttachmentRepository


class TestAttachmentModelUnified(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()
        cls.Attachment = cls.env["ir.attachment"].sudo()

    def _make_account(self, *, email: str, tokens: list[str]):
        server = self.FetchmailServer.create(
            {
                "name": "Server",
                "server_type": "imap",
                "server": "imap.example.com",
                "port": 993,
                "user": email,
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
                    "name": email,
                    "email": email,
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                    "imap_caps": {"tokens": tokens},
                }
            )

    def test_materialize_from_provider_imap_creates_ir_attachment_linked_to_index(self):
        account = self._make_account(email="imap@example.com", tokens=[])
        index_rec = self.Index.create(
            {
                "account_id": account.id,
                "provider": "imap",
                "folder": "INBOX",
                "uid": "1",
                "subject": "hello",
            }
        )

        repo = AttachmentRepository(self.env)
        service = AttachmentCacheService(repo)

        req = AttachmentMaterializeRequest(
            source=AttachmentSource.PROVIDER_IMAP,
            name="a.txt",
            mimetype="text/plain",
            size=5,
            account_id=account.id,
            content_id=None,
            provider_attachment_id="1",
            provider_message_id="1",
            provider_url="INBOX",
            attachment_data=b"hello",
        )
        dtos = service.materialize_from_provider(
            [req], index_rec.id, force_materialize=True
        )
        self.assertEqual(len(dtos), 1)

        att = self.Attachment.browse(dtos[0].id)
        self.assertTrue(bool(att.exists()))
        self.assertEqual(att.res_model, "maildesk.message_index")
        self.assertEqual(att.res_id, index_rec.id)
        self.assertTrue(bool(att.access_token))

    def test_gmail_open_materializes_attachments_to_ir_attachment(self):
        account = self._make_account(email="gmail@example.com", tokens=["X-GM-EXT-1"])
        index_rec = self.Index.create(
            {
                "account_id": account.id,
                "provider": "gmail",
                "folder": "INBOX",
                "uid": "MSG1",
                "subject": "hello",
            }
        )

        dummy_data = base64.urlsafe_b64encode(b"gmail-bytes").decode("utf-8")

        class DummyGet:
            def execute(self):
                return {"data": dummy_data}

        class DummyAttachments:
            def get(self, **_kw):
                return DummyGet()

        class DummyMessages:
            def attachments(self):
                return DummyAttachments()

        class DummyUsers:
            def messages(self):
                return DummyMessages()

        class DummyService:
            def users(self):
                return DummyUsers()

        adapter = OpenMessageAdapter(self.env)
        with patch.object(adapter, "gmail_build_service", return_value=DummyService()):
            out = adapter.materialize_provider_attachments(
                provider="gmail",
                account=account,
                folder=None,
                uid=index_rec.uid,
                attachments=[
                    {
                        "provider": "gmail",
                        "provider_message_id": "MSG1",
                        "provider_attachment_id": "ATT1",
                        "name": "a.txt",
                        "filename": "a.txt",
                        "mimetype": "text/plain",
                        "size": 10,
                        "content_id": "",
                        "contentId": "",
                        "is_inline": False,
                    }
                ],
                index_id=index_rec.id,
            )

        self.assertEqual(len(out), 1)
        self.assertIsInstance(out[0].get("id"), int)
        self.assertTrue(bool(out[0].get("access_token")))
        self.assertEqual(out[0].get("type"), "binary")
        self.assertNotIn("maildesk/attachment", str(out[0]))

        att = self.Attachment.browse(out[0]["id"])
        self.assertTrue(bool(att.exists()))
        self.assertEqual(att.res_model, "maildesk.message_index")
        self.assertEqual(att.res_id, index_rec.id)

    def test_outlook_open_materializes_attachments_to_ir_attachment(self):
        account = self._make_account(email="outlook@example.com", tokens=["MICROSOFT"])
        index_rec = self.Index.create(
            {
                "account_id": account.id,
                "provider": "outlook",
                "folder": "Inbox",
                "uid": "OMSG1",
                "subject": "hello",
            }
        )

        class DummyResp:
            status_code = 200
            content = b"outlook-bytes"

            def raise_for_status(self):
                return None

        class DummySess:
            def get(self, _url, timeout=60):
                return DummyResp()

        adapter = OpenMessageAdapter(self.env)
        with patch.object(
            adapter,
            "outlook_build_graph",
            return_value=(DummySess(), "https://graph.example"),
        ):
            out = adapter.materialize_provider_attachments(
                provider="outlook",
                account=account,
                folder=None,
                uid=index_rec.uid,
                attachments=[
                    {
                        "provider": "outlook",
                        "provider_message_id": "OMSG1",
                        "provider_attachment_id": "OATT1",
                        "name": "a.txt",
                        "filename": "a.txt",
                        "mimetype": "text/plain",
                        "size": 12,
                        "content_id": "",
                        "contentId": "",
                        "is_inline": False,
                    }
                ],
                index_id=index_rec.id,
            )

        self.assertEqual(len(out), 1)
        self.assertIsInstance(out[0].get("id"), int)
        self.assertTrue(bool(out[0].get("access_token")))
        self.assertEqual(out[0].get("type"), "binary")
        self.assertNotIn("maildesk/attachment", str(out[0]))

        att = self.Attachment.browse(out[0]["id"])
        self.assertTrue(bool(att.exists()))
        self.assertEqual(att.res_model, "maildesk.message_index")
        self.assertEqual(att.res_id, index_rec.id)
