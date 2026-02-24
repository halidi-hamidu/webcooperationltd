# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Sent Appender: Appends sent messages to the IMAP Sent folder.
Uses existing IMAP connection pool.
"""

import logging

from imapclient import SEEN

from ..providers.imap import get_pool

_logger = logging.getLogger(__name__)


class ImapSentAppender:
    """Appends messages to IMAP Sent folder."""

    def __init__(self, env):
        """
        Initialize ImapSentAppender.

        Args:
            env: Odoo environment
        """
        self._env = env

    def append(self, account, message):
        """
        Append a message to the account's Sent folder.

        Args:
            account: mailbox.account record
            message: email.message.EmailMessage object
        """
        # Caller (SendEmail) controls policy via 'append_sent_to_imap' flag.
        # If we are here, we MUST append.

        Folder = self._env["mailbox.folder"]
        sent_folder = None

        fld = Folder.search(
            [("account_id", "=", account.id), ("folder_type", "=", "sent")],
            limit=1,
        )
        if fld:
            sent_folder = fld.imap_name or fld.name

        if not sent_folder:
            fld = Folder.search(
                [
                    ("account_id", "=", account.id),
                    "|",
                    ("imap_name", "ilike", "sent"),
                    ("name", "ilike", "sent"),
                ],
                limit=1,
            )
            if fld:
                sent_folder = fld.imap_name or fld.name

        if not sent_folder:
            sent_folder = "Sent"

        # Defensive privacy guarantee: Bcc must never be serialized into Sent.
        for h in ("Bcc", "Resent-Bcc"):
            if h in message:
                del message[h]

        raw_bytes = message.as_bytes()

        pool = get_pool(account)
        try:
            with pool.session() as client:
                client.append(sent_folder, raw_bytes, flags=(SEEN,))
        except Exception:
            _logger.exception(
                "Failed to append sent message to IMAP Sent for account %s",
                account.id,
            )
