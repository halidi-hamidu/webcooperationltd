# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Connection Pool

Manages pooled, authenticated IMAP connections for classic username/password accounts.
"""

from contextlib import contextmanager, suppress
from queue import Queue

from imapclient import IMAPClient
from odoo.exceptions import UserError


class IMAPClientWithAuth(IMAPClient):
    """Extended IMAP client that tracks selected folder."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("ssl", True)
        kwargs.setdefault("use_uid", True)
        kwargs.setdefault("timeout", 30)
        super().__init__(*args, **kwargs)
        self._selected_folder = None

    @property
    def selected_folder(self):
        return self._selected_folder

    def select_folder(self, mailbox, readonly=False):
        res = super().select_folder(mailbox, readonly=readonly)
        self._selected_folder = mailbox
        return res

    def folder_status(self, folder, fields):
        return super().folder_status(folder, fields)

    def status(self, folder, fields):
        """
        Delegate to folder_status (correct IMAPClient API).
        Provides status() alias for cleaner code.
        """
        return self.folder_status(folder, fields)


class MailDeskIMAPPool:
    """Bounded pool of authenticated IMAP clients for a single account."""

    def __init__(self, account, size=5):
        self.env = account.env
        """
        Initialize a bounded pool of authenticated IMAP clients for a classic
        username/password account. The constructor validates server settings,
        blocks OAuth accounts, and pre-populates the queue with logged-in
        clients so callers can borrow connections without incurring login cost
        on every operation.
        """
        server = account.mail_server_id
        if not server:
            raise UserError(self.env._("Incoming fetchmail.server is not configured"))

        server_type = (getattr(server, "server_type", "") or "").lower()
        if server_type in ("gmail", "outlook", "ms365", "microsoft", "office365"):
            return

        self.account_id = account.id

        self.host = server.server
        self.port = int(server.port or 993)
        self.is_ssl = bool(server.is_ssl)

        self.username = (server.user or account.email or "").strip()
        self.password = getattr(server, "password", None) or ""

        if not self.host:
            raise UserError(self.env._("IMAP host is not set on fetchmail.server"))
        if not self.username or not self.password:
            raise UserError(
                self.env._("IMAP username/password are not set on fetchmail.server")
            )

        self.size = size
        self.pool = Queue(maxsize=size)
        for _i in range(size):
            self.pool.put(self._create_client())

    def _create_client(self):
        """
        Build and authenticate a single IMAP client with UTF8 support when
        advertised. If login fails the client is closed and the error surfaced,
        ensuring the pool never returns half-authenticated connections.
        """
        c = IMAPClientWithAuth(
            host=self.host,
            port=self.port,
            ssl=self.is_ssl,
            use_uid=True,
        )
        try:
            c.login(self.username, self.password)
        except Exception as e:
            with suppress(Exception):
                c.logout()
            raise Exception(f"IMAP password login failed: {e}")

        with suppress(Exception):
            caps = c.capabilities() or []
            if (b"UTF8=ACCEPT" in caps) or ("UTF8=ACCEPT" in caps):
                c.enable("UTF8=ACCEPT")
        return c

    @contextmanager
    def session(self, ensure_selected=None, readonly=True):
        """
        Yield a pooled IMAP client, reviving dead connections with a fresh login
        and optionally selecting the requested folder. Connections are returned
        to the queue after use, with broken clients discarded to keep the pool
        healthy under transient network errors.
        """
        c = self.pool.get()
        try:
            try:
                c.noop()
            except Exception:
                c = self._recreate(c)
            if (
                ensure_selected
                and getattr(c, "selected_folder", None) != ensure_selected
            ):
                c.select_folder(ensure_selected, readonly=readonly)
            yield c
        finally:
            try:
                self.pool.put(c)
            except Exception:
                with suppress(Exception):
                    c.logout()

    def _recreate(self, dead):
        """
        Dispose of a failed IMAP client and replace it with a new authenticated
        instance. Logout errors are ignored so pool recovery is resilient to
        partially closed sockets.
        """
        with suppress(Exception):
            dead.logout()
        return self._create_client()
