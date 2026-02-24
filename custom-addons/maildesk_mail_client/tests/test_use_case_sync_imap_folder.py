# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/sync_imap_folder.py`.

Focus: deterministic incremental sync behavior (UIDNEXT detection, SSOT upsert,
and notifier emissions) without external IMAP connections.
Layer: tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.sync_imap_folder import SyncImapFolderIncremental
from ..domain.contracts import Message
from .common import FakeNotifier


class TestSyncImapFolderIncremental(TransactionCase):
    """Validate IMAP incremental sync invariants."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()

    def _make_imap_account_and_folder(self):
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
            account = self.Account.create(
                {
                    "name": "IMAP Account",
                    "email": "imap@example.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                    "imap_caps": {},
                }
            )
        folder = self.Folder.create(
            {
                "name": "INBOX",
                "imap_name": "INBOX",
                "account_id": account.id,
                "sync_state": "incremental",
                "needs_sync": True,
                "uid_validity": 1,
                "last_uid": 0,
                "sync_modseq": "0",
                "unread_count": 0,
            }
        )
        return account, folder

    def test_incremental_sync_inserts_new_messages_and_emits_notifications(self):
        """New UIDs are upserted into SSOT and emitted via notifier (no network)."""

        account, folder = self._make_imap_account_and_folder()
        notifier = FakeNotifier()

        class DummyClient:
            def select_folder(self, _name, readonly=True):
                return {b"UIDVALIDITY": 1, b"UIDNEXT": 3, b"HIGHESTMODSEQ": None}

            def logout(self):
                return None

            def has_capability(self, _cap):
                return False

            def search(self, _query):
                return [1, 2]

        def _fake_fetch_message_batch(_client, _folder_name, _account, uids):
            now = datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
            out = []
            for uid in uids:
                out.append(
                    Message(
                        id=str(uid),
                        thread_id=str(uid),
                        account_id=account.id,
                        message_header_id=f"<m{uid}@example.com>",
                        in_reply_to="",
                        references="",
                        date=now,
                        subject=f"Subject {uid}",
                        email_from="sender@example.com",
                        sender_display_name="Sender",
                        to_display="imap@example.com",
                        cc_display="",
                        bcc_display="",
                        snippet="Preview",
                        is_read=False,
                        is_starred=False,
                        has_attachments=False,
                        metadata={"imap_uid": uid},
                    )
                )
            return out

        use_case = SyncImapFolderIncremental(self.env, notifier=notifier)

        with (
            patch.object(use_case, "_open_client", return_value=DummyClient()),
            patch.object(
                use_case, "_fetch_message_batch", side_effect=_fake_fetch_message_batch
            ),
            patch.object(use_case, "_sync_flags", return_value=None),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.try_acquire",
                return_value=True,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.release",
                return_value=True,
            ),
        ):
            res = use_case.execute(account.id)

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("total_fetched"), 2)

        folder.invalidate_recordset()
        self.assertEqual(folder.last_uid, 2)
        self.assertFalse(folder.needs_sync)
        self.assertEqual(folder.unread_count, 2)

        count = self.Index.search_count(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", "INBOX"),
            ]
        )
        self.assertEqual(count, 2)

        event_names = [c.name for c in notifier.calls]
        self.assertIn("notify_messages_added", event_names)
        self.assertIn("notify_unread_count_changed", event_names)

    def test_incremental_sync_does_not_advance_cursor_when_fetch_returns_no_records(
        self,
    ):
        """
        Regression guard:
        If the server reports new UIDs but the fetch/parsing pipeline returns no records,
        the sync must NOT advance last_uid (otherwise messages become permanently missing).
        """
        account, folder = self._make_imap_account_and_folder()
        notifier = FakeNotifier()

        class DummyClient:
            def select_folder(self, _name, readonly=True):
                return {b"UIDVALIDITY": 1, b"UIDNEXT": 3, b"HIGHESTMODSEQ": None}

            def logout(self):
                return None

            def search(self, _query):
                return [1, 2]

        use_case = SyncImapFolderIncremental(self.env, notifier=notifier)

        with (
            patch.object(use_case, "_open_client", return_value=DummyClient()),
            patch.object(use_case, "_fetch_message_batch", return_value=[]),
            patch.object(use_case, "_sync_flags", return_value=None),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.try_acquire",
                return_value=True,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.release",
                return_value=True,
            ),
        ):
            res = use_case.execute(account.id)

        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("total_fetched"), 0)

        folder.invalidate_recordset()
        self.assertEqual(folder.last_uid, 0)
        self.assertTrue(folder.needs_sync)
        self.assertTrue(bool(folder.last_error))

        count = self.Index.search_count(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", "INBOX"),
            ]
        )
        self.assertEqual(count, 0)

    def test_inbox_delivery_does_not_reconcile_local_pending_sent(self):
        """
        Regression guard (SSOT identity):
        An INBOX delivery MUST NOT reconcile (overwrite) a local_pending Sent row,
        even if it contains correlation/threading headers.
        """
        account, inbox = self._make_imap_account_and_folder()
        inbox.write({"last_uid": 216})
        notifier = FakeNotifier()

        # Local pending entry created by send_email (typically in Sent with a local UID).
        local_uid = "local-550e8400-e29b-41d4-a716-446655440000"
        mid = "<m217@example.com>"
        outgoing_id = "maildesk-123"
        self.Index.create(
            {
                "account_id": account.id,
                "provider": "imap",
                "folder": "Sent",
                "uid": local_uid,
                "message_id": mid,
                "outgoing_id": outgoing_id,
                "from_addr": "imap@example.com",
                "to_addrs": "to@example.com",
                "subject": "Pending",
                "date": datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
                "is_read": True,
                "is_starred": False,
                "local_pending": True,
            }
        )

        class DummyClient:
            def select_folder(self, _name, readonly=True):
                return {b"UIDVALIDITY": 1, b"UIDNEXT": 218, b"HIGHESTMODSEQ": None}

            def logout(self):
                return None

            def has_capability(self, _cap):
                return False

            def search(self, _query):
                # Provider state capture after sync.
                return [217]

        def _fake_fetch_message_batch(_client, _folder_name, _account, uids):
            now = datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
            uid = int(uids[0])
            return [
                Message(
                    id=str(uid),
                    thread_id=str(uid),
                    account_id=account.id,
                    message_header_id="<reply-217@example.com>",
                    in_reply_to=mid,
                    references=mid,
                    date=now,
                    subject="Reconciled",
                    email_from="sender@example.com",
                    sender_display_name="Sender",
                    to_display="imap@example.com",
                    cc_display="",
                    bcc_display="",
                    snippet="Preview",
                    outgoing_id=outgoing_id,
                    is_read=False,
                    is_starred=False,
                    has_attachments=False,
                    metadata={"imap_uid": uid},
                )
            ]

        use_case = SyncImapFolderIncremental(self.env, notifier=notifier)
        with (
            patch.object(use_case, "_open_client", return_value=DummyClient()),
            patch.object(
                use_case, "_fetch_message_batch", side_effect=_fake_fetch_message_batch
            ),
            patch.object(use_case, "_sync_flags", return_value=None),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.try_acquire",
                return_value=True,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.release",
                return_value=True,
            ),
        ):
            res = use_case.execute(account.id)

        self.assertTrue(res.get("ok"))

        # Local pending Sent placeholder remains untouched.
        pending = self.Index.search(
            [("account_id", "=", account.id), ("uid", "=", local_uid)], limit=1
        )
        self.assertTrue(bool(pending))
        self.assertTrue(bool(pending.local_pending))
        self.assertEqual(pending.folder, "Sent")

        # INBOX delivery is inserted as a new SSOT row (distinct delivery).
        inbox_row = self.Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", "INBOX"),
                ("uid", "=", "217"),
            ],
            limit=1,
        )
        self.assertTrue(bool(inbox_row))
        self.assertEqual(inbox_row.message_id, "<reply-217@example.com>")

        event_names = [c.name for c in notifier.calls]
        self.assertIn("notify_messages_added", event_names)
        self.assertNotIn("notify_messages_moved", event_names)

    def test_reconcile_local_pending_sent_confirmation_updates_uid(self):
        """
        Outbound confirmation (Sent copy) updates a local_pending row in-place.

        Primary key: outgoing_id (X-MailDesk-Outgoing-ID).
        Must NOT depend on folder_type being correctly classified as 'sent'.
        """
        account, inbox = self._make_imap_account_and_folder()
        notifier = FakeNotifier()

        _sent = self.Folder.create(
            {
                "name": "Sent",
                "imap_name": "Sent",
                "account_id": account.id,
                "sync_state": "incremental",
                "needs_sync": True,
                "uid_validity": 1,
                "last_uid": 216,
                "sync_modseq": "0",
                "unread_count": 0,
                # Explicitly wrong: confirmation must not depend on folder_type.
                "folder_type": "other",
            }
        )
        inbox.write({"needs_sync": False, "last_uid": 0})

        local_uid = "local-550e8400-e29b-41d4-a716-446655440000"
        mid = "<m217@example.com>"
        outgoing_id = "maildesk-123"
        pending = self.Index.create(
            {
                "account_id": account.id,
                "provider": "imap",
                "folder": "Sent",
                "uid": local_uid,
                "message_id": mid,
                "outgoing_id": outgoing_id,
                "from_addr": "imap@example.com",
                "to_addrs": "to@example.com",
                "subject": "Pending",
                "date": datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
                "is_read": True,
                "is_starred": False,
                "local_pending": True,
            }
        )

        class DummyClient:
            def __init__(self):
                self._selected = None

            def select_folder(self, name, readonly=True):
                self._selected = name
                if name == "Sent":
                    return {b"UIDVALIDITY": 1, b"UIDNEXT": 218, b"HIGHESTMODSEQ": None}
                return {b"UIDVALIDITY": 1, b"UIDNEXT": 1, b"HIGHESTMODSEQ": None}

            def logout(self):
                return None

            def search(self, _query):
                if self._selected == "Sent":
                    return [217]
                return []

        def _fake_fetch_message_batch(_client, folder_name, _account, uids):
            now = datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
            uid = int(uids[0])
            if folder_name != "Sent":
                return []
            return [
                Message(
                    id=str(uid),
                    thread_id=str(uid),
                    account_id=account.id,
                    message_header_id=mid,
                    in_reply_to="",
                    references="",
                    date=now,
                    subject="Sent copy",
                    email_from="imap@example.com",
                    sender_display_name="Me",
                    to_display="to@example.com",
                    cc_display="",
                    bcc_display="",
                    snippet="Preview",
                    outgoing_id=outgoing_id,
                    is_read=True,
                    is_starred=False,
                    has_attachments=False,
                    metadata={"imap_uid": uid},
                )
            ]

        use_case = SyncImapFolderIncremental(self.env, notifier=notifier)
        with (
            patch.object(use_case, "_open_client", return_value=DummyClient()),
            patch.object(
                use_case, "_fetch_message_batch", side_effect=_fake_fetch_message_batch
            ),
            patch.object(use_case, "_sync_flags", return_value=None),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.try_acquire",
                return_value=True,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.release",
                return_value=True,
            ),
        ):
            res = use_case.execute(account.id)

        self.assertTrue(res.get("ok"))

        reconciled = self.Index.search(
            [("account_id", "=", account.id), ("message_id", "=", mid)], limit=1
        )
        self.assertTrue(bool(reconciled))
        self.assertEqual(reconciled.id, pending.id)
        self.assertFalse(bool(reconciled.local_pending))
        self.assertEqual(reconciled.folder, "Sent")
        self.assertEqual(reconciled.uid, "217")

        event_names = [c.name for c in notifier.calls]
        self.assertIn("notify_full_refresh", event_names)

    def test_reconcile_local_pending_fallback_by_message_id_when_outgoing_id_missing(
        self,
    ):
        """
        Fallback confirmation: if provider message lacks outgoing_id, allow Message-ID
        confirmation for local_pending rows with strict guards (same folder, sender match).
        """
        account, inbox = self._make_imap_account_and_folder()
        notifier = FakeNotifier()

        self.Folder.create(
            {
                "name": "Sent",
                "imap_name": "Sent",
                "account_id": account.id,
                "sync_state": "incremental",
                "needs_sync": True,
                "uid_validity": 1,
                "last_uid": 216,
                "sync_modseq": "0",
                "unread_count": 0,
                "folder_type": "other",
            }
        )
        inbox.write({"needs_sync": False, "last_uid": 0})

        local_uid = "local-550e8400-e29b-41d4-a716-446655440001"
        mid = "<m218@example.com>"
        outgoing_id = "maildesk-xyz"
        self.Index.create(
            {
                "account_id": account.id,
                "provider": "imap",
                "folder": "Sent",
                "uid": local_uid,
                "message_id": mid,
                "outgoing_id": outgoing_id,
                "from_addr": "imap@example.com",
                "to_addrs": "to@example.com",
                "subject": "Pending",
                "date": datetime.now(timezone.utc).replace(tzinfo=None),
                "is_read": True,
                "is_starred": False,
                "local_pending": True,
            }
        )

        class DummyClient:
            def __init__(self):
                self._selected = None

            def select_folder(self, name, readonly=True):
                self._selected = name
                if name == "Sent":
                    return {b"UIDVALIDITY": 1, b"UIDNEXT": 219, b"HIGHESTMODSEQ": None}
                return {b"UIDVALIDITY": 1, b"UIDNEXT": 1, b"HIGHESTMODSEQ": None}

            def logout(self):
                return None

            def search(self, _query):
                if self._selected == "Sent":
                    return [218]
                return []

        def _fake_fetch_message_batch(_client, folder_name, _account, uids):
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            uid = int(uids[0])
            if folder_name != "Sent":
                return []
            return [
                Message(
                    id=str(uid),
                    thread_id=str(uid),
                    account_id=account.id,
                    message_header_id=mid,
                    in_reply_to="",
                    references="",
                    date=now,
                    subject="Sent copy",
                    email_from="imap@example.com",
                    sender_display_name="Me",
                    to_display="to@example.com",
                    cc_display="",
                    bcc_display="",
                    snippet="Preview",
                    outgoing_id="",
                    is_read=True,
                    is_starred=False,
                    has_attachments=False,
                    metadata={"imap_uid": uid},
                )
            ]

        use_case = SyncImapFolderIncremental(self.env, notifier=notifier)
        with (
            patch.object(use_case, "_open_client", return_value=DummyClient()),
            patch.object(
                use_case, "_fetch_message_batch", side_effect=_fake_fetch_message_batch
            ),
            patch.object(use_case, "_sync_flags", return_value=None),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.try_acquire",
                return_value=True,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.release",
                return_value=True,
            ),
        ):
            res = use_case.execute(account.id)

        self.assertTrue(res.get("ok"))

    def test_duplicate_provider_sent_copies_with_same_outgoing_id_do_not_create_two_rows(
        self,
    ):
        """
        If a provider exposes multiple Sent copies with the same outgoing_id, keep SSOT to
        one row (do not insert a second row for the same outgoing_id).
        """
        account, inbox = self._make_imap_account_and_folder()
        notifier = FakeNotifier()

        self.Folder.create(
            {
                "name": "Sent",
                "imap_name": "Sent",
                "account_id": account.id,
                "sync_state": "incremental",
                "needs_sync": True,
                "uid_validity": 1,
                "last_uid": 216,
                "sync_modseq": "0",
                "unread_count": 0,
                "folder_type": "other",
            }
        )
        inbox.write({"needs_sync": False, "last_uid": 0})

        mid = "<m219@example.com>"
        outgoing_id = "maildesk-dupe"
        self.Index.create(
            {
                "account_id": account.id,
                "provider": "imap",
                "folder": "Sent",
                "uid": "local-550e8400-e29b-41d4-a716-446655440002",
                "message_id": mid,
                "outgoing_id": outgoing_id,
                "from_addr": "imap@example.com",
                "to_addrs": "to@example.com",
                "subject": "Pending",
                "date": datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None),
                "is_read": True,
                "is_starred": False,
                "local_pending": True,
            }
        )

        class DummyClient:
            def __init__(self):
                self._selected = None

            def select_folder(self, name, readonly=True):
                self._selected = name
                if name == "Sent":
                    return {b"UIDVALIDITY": 1, b"UIDNEXT": 220, b"HIGHESTMODSEQ": None}
                return {b"UIDVALIDITY": 1, b"UIDNEXT": 1, b"HIGHESTMODSEQ": None}

            def logout(self):
                return None

            def search(self, _query):
                if self._selected == "Sent":
                    return [217, 218]
                return []

        def _fake_fetch_message_batch(_client, folder_name, _account, uids):
            now = datetime(2025, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
            out = []
            for uid in uids:
                if folder_name != "Sent":
                    continue
                out.append(
                    Message(
                        id=str(uid),
                        thread_id=str(uid),
                        account_id=account.id,
                        message_header_id=mid,
                        in_reply_to="",
                        references="",
                        date=now,
                        subject="Sent copy",
                        email_from="imap@example.com",
                        sender_display_name="Me",
                        to_display="to@example.com",
                        cc_display="",
                        bcc_display="",
                        snippet="Preview",
                        outgoing_id=outgoing_id,
                        is_read=True,
                        is_starred=False,
                        has_attachments=False,
                        metadata={"imap_uid": int(uid)},
                    )
                )
            return out

        use_case = SyncImapFolderIncremental(self.env, notifier=notifier)
        with (
            patch.object(use_case, "_open_client", return_value=DummyClient()),
            patch.object(
                use_case, "_fetch_message_batch", side_effect=_fake_fetch_message_batch
            ),
            patch.object(use_case, "_sync_flags", return_value=None),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.try_acquire",
                return_value=True,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.models.maildesk_account_lease.MailDeskAccountLease.release",
                return_value=True,
            ),
        ):
            res = use_case.execute(account.id)

        self.assertTrue(res.get("ok"))

        rows = self.Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", "Sent"),
                ("outgoing_id", "=", outgoing_id),
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.uid, "217")
        self.assertFalse(bool(rows.local_pending))

        unexpected = self.Index.search(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", "Sent"),
                ("uid", "=", "218"),
            ],
            limit=1,
        )
        self.assertFalse(bool(unexpected))
