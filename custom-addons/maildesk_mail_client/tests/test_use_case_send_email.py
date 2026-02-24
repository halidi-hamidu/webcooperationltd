# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/send_email.py`.

Focus: send orchestration (MIME build, SMTP send, SSOT-on-send, ui_cache hydration)
without external SMTP/IMAP activity.
Layer: tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from ..application.use_cases.send_email import SendEmail, SendEmailParams


class TestSendEmail(TransactionCase):
    """Validate send email invariants."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()
        cls.Folder = cls.env["mailbox.folder"].sudo()
        cls.Draft = cls.env["maildesk.draft"].sudo()
        cls.Index = cls.env["maildesk.message_index"].sudo()
        cls.UICache = cls.env["maildesk.ui_cache"].sudo()

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
                    "append_sent_to_imap": True,
                }
            )

    def test_send_creates_local_ssot_entry_and_hydrates_ui_cache(self):
        """Send creates a local_pending SSOT record and a ui_cache body entry."""

        account = self._make_imap_account()
        self.Folder.create(
            {
                "name": "Sent",
                "imap_name": "Sent",
                "folder_type": "sent",
                "account_id": account.id,
                "sync_state": "incremental",
            }
        )

        draft = self.Draft.create(
            {
                "account_id": account.id,
                "subject": "Draft Subject",
                "body_html": "<p>Draft Body</p>",
                "to_emails": "to@example.com",
                "cc_emails": "",
                "bcc_emails": "",
            }
        )

        msg_obj = object()
        smtp_send = MagicMock()
        imap_append = MagicMock()

        with (
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.send_email.AccessControl.check_account_access",
                return_value=None,
            ),
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.send_email.MimeBuilder.build",
                return_value=(msg_obj, "<mid@example.com>"),
            ),
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.send_email.SmtpSender.send",
                side_effect=lambda _account, _msg, envelope_to_addrs=None: smtp_send(
                    _account.id, _msg
                ),
            ),
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.send_email.ImapSentAppender.append",
                side_effect=lambda _account, _msg: imap_append(_account.id, _msg),
            ),
            patch(
                "odoo.addons.maildesk_mail_client.application.use_cases.send_email.BusNotificationAdapter.notify_messages_added",
                return_value=None,
            ),
        ):
            res = SendEmail(self.env).execute(
                SendEmailParams(
                    draft_id=draft.id,
                    # Explicitly omit subject/body/to: use draft fallback behavior.
                    subject=None,
                    body_html=None,
                    to=[],
                    cc=[],
                    bcc=[],
                )
            )

        self.assertEqual(res.get("message_id"), "<mid@example.com>")
        smtp_send.assert_called_once_with(account.id, msg_obj)
        imap_append.assert_called_once_with(account.id, msg_obj)

        self.assertFalse(bool(self.Draft.browse(draft.id).exists()))

        idx = self.Index.search(
            [
                ("account_id", "=", account.id),
                ("message_id", "=", "<mid@example.com>"),
            ],
            limit=1,
        )
        self.assertTrue(bool(idx))
        self.assertTrue(bool(idx.local_pending))
        self.assertEqual(idx.folder, "Sent")
        self.assertTrue(idx.uid.startswith("local-"))

        cache = self.UICache.search([("index_id", "=", idx.id)], limit=1)
        self.assertTrue(bool(cache))
        body_payload = (cache.json_cache or {}).get("body") or {}
        self.assertEqual(body_payload.get("body_html"), "<p>Draft Body</p>")
