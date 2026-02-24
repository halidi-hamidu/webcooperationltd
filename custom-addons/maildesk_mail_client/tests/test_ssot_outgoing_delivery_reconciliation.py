# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""SSOT outbound confirmation tests (outgoing_id-based reconciliation).

These tests focus on provider sync paths confirming SSOT-on-send local_pending rows
in-place, ensuring stable index_id and no duplicate Sent messages.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.sync_gmail_incremental import SyncGmailIncremental
from ..application.use_cases.sync_outlook_delta import SyncOutlookDelta
from ..domain.contracts import Message
from .common import FakeNotifier


class TestSSOTOutgoingDeliveryReconciliation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()

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

    def test_gmail_incremental_confirms_local_pending_in_place_by_outgoing_id(self):
        account = self._make_account(email="gmail@example.com", tokens=["X-GM-EXT-1"])

        # Explicitly wrong: confirmation must not depend on folder_type.
        self.Folder.create(
            {
                "name": "Sent",
                "imap_name": "Sent",
                "account_id": account.id,
                "sync_state": "incremental",
                "needs_sync": True,
                "uid_validity": 1,
                "last_uid": 0,
                "sync_modseq": "0",
                "unread_count": 0,
                "folder_type": "other",
            }
        )

        outgoing_id = "maildesk-gmail-1"
        mid = "<gmail-1@example.com>"
        pending = self.Index.create(
            {
                "account_id": account.id,
                "provider": "gmail",
                "folder": "Sent",
                "uid": "local-1",
                "message_id": mid,
                "outgoing_id": outgoing_id,
                "from_addr": account.email,
                "to_addrs": "to@example.com",
                "subject": "Pending",
                "date": datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
                "is_read": True,
                "is_starred": False,
                "local_pending": True,
            }
        )

        msg = Message(
            id="GMSG1",
            thread_id="T1",
            account_id=account.id,
            message_header_id=mid,
            in_reply_to="",
            references="",
            date=datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
            subject="Sent copy",
            email_from=account.email,
            sender_display_name="Me",
            to_display="to@example.com",
            cc_display="",
            bcc_display="",
            snippet="Preview",
            outgoing_id=outgoing_id,
            is_read=True,
            is_starred=False,
            has_attachments=False,
            metadata={"label_ids": ["1"]},
        )

        use_case = SyncGmailIncremental(self.env, notifier=FakeNotifier())
        deleted_by_folder = {}
        added_by_folder, _flags_changed, refresh_folders = use_case._upsert_messages(
            account,
            [msg],
            label_id_map={"1": "SENT"},
            folder_map={"sent": "Sent"},
            add_all_mail=False,
            deleted_by_folder=deleted_by_folder,
            new_message_ids={str(msg.id)},
        )

        self.assertFalse(bool(added_by_folder))
        self.assertIn("Sent", refresh_folders)

        pending.invalidate_recordset()
        self.assertEqual(pending.uid, "GMSG1")
        self.assertFalse(bool(pending.local_pending))

        confirmed = self.Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "gmail"),
                ("folder", "=", "Sent"),
                ("uid", "=", "GMSG1"),
            ],
            limit=1,
        )
        self.assertTrue(bool(confirmed))
        self.assertEqual(confirmed.id, pending.id)

        self.assertEqual(
            self.Index.search_count(
                [
                    ("account_id", "=", account.id),
                    ("provider", "=", "gmail"),
                    ("folder", "=", "Sent"),
                ]
            ),
            1,
        )

    def test_outlook_delta_confirms_local_pending_in_place_by_outgoing_id(self):
        account = self._make_account(email="outlook@example.com", tokens=["MICROSOFT"])

        self.Folder.create(
            {
                "name": "Sent",
                "imap_name": "Sent",
                "account_id": account.id,
                "sync_state": "incremental",
                "needs_sync": True,
                "uid_validity": 1,
                "last_uid": 0,
                "unread_count": 0,
                "folder_type": "other",
            }
        )

        outgoing_id = "maildesk-outlook-1"
        mid = "<outlook-1@example.com>"
        pending = self.Index.create(
            {
                "account_id": account.id,
                "provider": "outlook",
                "folder": "Sent",
                "uid": "local-1",
                "message_id": mid,
                "outgoing_id": outgoing_id,
                "from_addr": account.email,
                "to_addrs": "to@example.com",
                "subject": "Pending",
                "date": datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
                "is_read": True,
                "is_starred": False,
                "local_pending": True,
            }
        )

        msg = Message(
            id="OID1",
            thread_id="T1",
            account_id=account.id,
            message_header_id=mid,
            in_reply_to="",
            references="",
            date=datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
            subject="Sent copy",
            email_from=account.email,
            sender_display_name="Me",
            to_display="to@example.com",
            cc_display="",
            bcc_display="",
            snippet="Preview",
            outgoing_id=outgoing_id,
            is_read=True,
            is_starred=False,
            has_attachments=False,
            metadata={},
        )

        notifier = FakeNotifier()
        use_case = SyncOutlookDelta(self.env, notifier=notifier, lease_ttl_seconds=60)

        added_by_folder = {}
        flags_changed = {}
        moved_by_folder = {}
        refresh_folders = set()

        with patch.object(use_case, "_message_from_delta", return_value=msg):
            use_case._process_message_item(
                account=account,
                item={"id": "ignored"},
                folder_name="Sent",
                is_initialized=True,
                added_by_folder=added_by_folder,
                flags_changed=flags_changed,
                moved_by_folder=moved_by_folder,
                refresh_folders=refresh_folders,
            )

        self.assertFalse(bool(added_by_folder))
        self.assertIn("Sent", refresh_folders)

        pending.invalidate_recordset()
        self.assertEqual(pending.uid, "OID1")
        self.assertFalse(bool(pending.local_pending))

        self.assertEqual(
            self.Index.search_count(
                [
                    ("account_id", "=", account.id),
                    ("provider", "=", "outlook"),
                    ("folder", "=", "Sent"),
                ]
            ),
            1,
        )
