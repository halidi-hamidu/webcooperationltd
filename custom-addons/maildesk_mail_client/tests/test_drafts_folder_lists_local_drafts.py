# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Draft folder listing tests.

Focus:
- Saving a draft must assign ownership to the calling user (not OdooBot).
- Drafts folder list must include internal drafts (maildesk.draft) even when
  SSOT has zero indexed messages for that folder.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestDraftsFolderListing(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Draft = cls.env["maildesk.draft"].sudo()
        cls.Sync = cls.env["mailbox.sync"].sudo()

    def _make_account_and_drafts_folder(self, email: str):
        server = self.FetchmailServer.create(
            {
                "name": "IMAP Server",
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
            account = self.Account.create(
                {
                    "name": email,
                    "email": email,
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                }
            )

        drafts_folder = self.Folder.create(
            {
                "name": "Drafts",
                "imap_name": "Drafts",
                "folder_type": "drafts",
                "account_id": account.id,
                "sync_state": "incremental",
            }
        )
        return account, drafts_folder

    def test_drafts_folder_includes_internal_drafts_even_without_ssot(self):
        account, drafts_folder = self._make_account_and_drafts_folder("d@example.com")

        draft_id = self.env["mailbox.sync"].save_draft(
            account_id=account.id,
            subject="Hello",
            body_html="<p>Body</p>",
            to_emails="to@example.com",
            cc_emails="",
            bcc_emails="",
            attachment_ids=[],
        )

        draft = self.Draft.browse(draft_id)
        self.assertTrue(bool(draft.exists()))
        self.assertEqual(draft.user_id.id, self.env.user.id)

        res = self.Sync.message_search_load(
            account_id=account.id,
            folder_id=drafts_folder.id,
            offset=0,
            limit=30,
        )

        records = res.get("records") or []
        self.assertEqual(res.get("totalMessagesCount"), 1)
        self.assertFalse(res.get("ssot_miss", False))
        self.assertTrue(
            any(r.get("is_internal_draft") and r.get("id") == draft_id for r in records)
        )

        opened = self.Sync.get_message_with_attachments(
            {
                "uid": draft_id,
                "folder_id": drafts_folder.id,
                "account_id": account.id,
                "is_internal_draft": True,
            }
        )
        self.assertEqual(opened.get("id"), draft_id)
        self.assertTrue(opened.get("is_local_draft"))
        self.assertEqual(opened.get("folder_id"), drafts_folder.id)
        self.assertTrue(str(opened.get("msg_key") or "").endswith(f"|draft|{draft_id}"))
