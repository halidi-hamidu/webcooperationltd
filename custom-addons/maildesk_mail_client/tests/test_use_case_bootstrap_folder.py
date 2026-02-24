# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/bootstrap_folder.py`.

Focus: deterministic IMAP bootstrap behavior (SSOT population + folder state
transitions) without external network access.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.bootstrap_folder import BootstrapFolder
from .common import DummyImapAddress, DummyImapEnvelope, context_manager_return


class TestBootstrapFolderImap(TransactionCase):
    """Validate IMAP folder bootstrap invariants."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Config = cls.env["ir.config_parameter"].sudo()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()

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

    def test_bootstrap_imap_creates_ssot_and_transitions_state(self):
        """Bootstrap inserts SSOT rows and moves folder to incremental with correct cursors."""

        self.Config.set_param("maildesk.backfill_bootstrap_max", "2")
        self.Config.set_param("maildesk.backfill_mode", "progressive")

        account = self._make_imap_account()
        folder = self.Folder.create(
            {
                "name": "INBOX",
                "imap_name": "INBOX",
                "account_id": account.id,
                "sync_state": "backfill_pending",
            }
        )

        class DummyClient:
            def select_folder(self, _name, readonly=True):
                return {b"UIDNEXT": 6, b"EXISTS": 5}

            def fetch(self, uids, _fields):
                addr = DummyImapAddress(
                    name=b"Sender",
                    mailbox=b"sender",
                    host=b"example.com",
                )
                env = DummyImapEnvelope(
                    subject=b"Hello",
                    from_=[addr],
                    to=[DummyImapAddress(mailbox=b"imap", host=b"example.com")],
                    date=b"Mon, 01 Jan 2025 00:00:00 +0000",
                )
                out = {}
                for uid in uids:
                    out[int(uid)] = {
                        b"ENVELOPE": env,
                        b"FLAGS": [b"\\Seen"],
                        b"INTERNALDATE": None,
                        b"RFC822.SIZE": 123,
                        b"BODYSTRUCTURE": None,
                        b"BODY[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)]": (
                            b"Message-ID: <m@example.com>\r\n"
                            b"In-Reply-To: <p@example.com>\r\n"
                            b"References: <r@example.com>\r\n"
                        ),
                        b"BODY[1]": b"",
                        b"BODY[TEXT]": b"",
                    }
                return out

        with patch(
            "odoo.addons.maildesk_mail_client.application.use_cases.bootstrap_folder.build_authenticated_imap_client",
            autospec=True,
            side_effect=lambda env, acc: context_manager_return(DummyClient()),
        ):
            result = BootstrapFolder(self.env).execute(folder.id)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("mode"), "bootstrap")
        self.assertEqual(result.get("fetched"), 2)

        folder.invalidate_recordset()
        self.assertEqual(folder.sync_state, "incremental")
        self.assertEqual(folder.last_uid, 5)
        self.assertEqual(folder.backfill_last_uid, 3)
        self.assertEqual(folder.backfill_fetched_count, 2)
        self.assertEqual(folder.backfill_total_estimate, 5)

        count = self.Index.search_count(
            [
                ("account_id", "=", account.id),
                ("provider", "=", "imap"),
                ("folder", "=", "INBOX"),
            ]
        )
        self.assertEqual(count, 2)

    def test_bootstrap_imap_does_not_corrupt_state_when_fetch_returns_empty(self):
        """Bootstrap must not transition to incremental if no messages were fetched."""

        self.Config.set_param("maildesk.backfill_bootstrap_max", "2")
        self.Config.set_param("maildesk.backfill_mode", "progressive")

        account = self._make_imap_account()
        folder = self.Folder.create(
            {
                "name": "INBOX",
                "imap_name": "INBOX",
                "account_id": account.id,
                "sync_state": "backfill_pending",
                "last_uid": 0,
            }
        )

        class DummyClient:
            def select_folder(self, _name, readonly=True):
                return {b"UIDNEXT": 6, b"EXISTS": 5}

            def fetch(self, _uids, _fields):
                return {}

        with patch(
            "odoo.addons.maildesk_mail_client.application.use_cases.bootstrap_folder.build_authenticated_imap_client",
            autospec=True,
            side_effect=lambda env, acc: context_manager_return(DummyClient()),
        ):
            result = BootstrapFolder(self.env).execute(folder.id)

        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("reason"), "fetch_failed")

        folder.invalidate_recordset()
        self.assertEqual(folder.sync_state, "backfill_pending")
        self.assertEqual(folder.last_uid, 0)

    def test_bootstrap_imap_marks_folder_empty_when_exists_is_zero(self):
        """
        Bootstrap must treat EXISTS=0 as empty even if UIDNEXT > 1.

        Some IMAP servers keep UIDNEXT increasing even after all messages were
        deleted. In that case, attempting to fetch UIDs yields zero messages and
        the folder must still be transitioned to incremental to avoid an
        indefinite backfill_pending loop.
        """

        self.Config.set_param("maildesk.backfill_bootstrap_max", "50")
        self.Config.set_param("maildesk.backfill_mode", "progressive")

        account = self._make_imap_account()
        folder = self.Folder.create(
            {
                "name": "Junk",
                "imap_name": "Junk",
                "account_id": account.id,
                "sync_state": "backfill_pending",
                "last_uid": 0,
            }
        )

        class DummyClient:
            def select_folder(self, _name, readonly=True):
                return {b"UIDNEXT": 42, b"EXISTS": 0}

            def fetch(self, _uids, _fields):
                raise AssertionError("fetch() must not be called for empty folders")

        with patch(
            "odoo.addons.maildesk_mail_client.application.use_cases.bootstrap_folder.build_authenticated_imap_client",
            autospec=True,
            side_effect=lambda env, acc: context_manager_return(DummyClient()),
        ):
            result = BootstrapFolder(self.env).execute(folder.id)

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("mode"), "empty")
        self.assertEqual(result.get("fetched"), 0)

        folder.invalidate_recordset()
        self.assertEqual(folder.sync_state, "incremental")
        self.assertTrue(bool(folder.backfill_completed_at))
        self.assertEqual(folder.last_uid, 0)
        self.assertEqual(folder.backfill_fetched_count, 0)
