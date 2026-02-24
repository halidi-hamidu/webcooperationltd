# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
SMTP Sender: Handles sending generic EmailMessage objects via SMTP.
Encapsulates connection management and error handling for Odoo's ir.mail_server.
"""

import logging
from email.utils import getaddresses

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SmtpSender:
    """Sends prepared EmailMessages via SMTP."""

    def __init__(self, env):
        """
        Initialize SmtpSender.

        Args:
            env: Odoo environment for accessing ir.mail_server
        """
        self._env = env

    def send(self, account, message, envelope_to_addrs=None):
        """
        Send an email message via the account's configured SMTP server.

        Args:
            account: mailbox.account record
            message: email.message.EmailMessage object to send
            envelope_to_addrs: Optional list of envelope recipient strings (To/Cc/Bcc);
                when provided, this MUST be used instead of parsing message headers.

        Raises:
            UserError: If SMTP server is not configured
        """
        smtp = account.sudo().mail_send_server_id
        if not smtp:
            raise UserError(self._env._("SMTP server not configured."))

        # Defensive privacy guarantee: Bcc must never be serialized.
        for h in ("Bcc", "Resent-Bcc"):
            if h in message:
                del message[h]

        # These are set by MTAs, not clients; remove if present to avoid poisoning.
        for h in ("Return-Path",):
            if h in message:
                del message[h]

        rcpt_values = envelope_to_addrs
        if not rcpt_values:
            rcpt_values = [
                str(message.get("To") or ""),
                str(message.get("Cc") or ""),
                str(message.get("Bcc") or ""),
            ]

        rcpt_addrs = []
        for _name, addr in getaddresses(rcpt_values):
            a = (addr or "").strip()
            if a and "\n" not in a and "\r" not in a:
                rcpt_addrs.append(a)

        # De-duplicate while preserving order
        seen = set()
        rcpt_addrs = [a for a in rcpt_addrs if not (a in seen or seen.add(a))]

        if not rcpt_addrs:
            raise UserError(self._env._("No recipients provided."))

        # Connect to SMTP server
        s = self._env["ir.mail_server"]._connect__(mail_server_id=smtp.id)
        try:
            try:
                # Prefer native SMTP.send_message (handles SMTPUTF8 when supported).
                s.send_message(
                    message,
                    from_addr=(account.email or None),
                    to_addrs=rcpt_addrs,
                )
            except Exception:
                raw_bytes = message.as_bytes()
                s.sendmail(account.email, rcpt_addrs, raw_bytes)
        finally:
            try:
                s.quit()
            except Exception as e:
                _logger.debug("ignored error: %s", e)
