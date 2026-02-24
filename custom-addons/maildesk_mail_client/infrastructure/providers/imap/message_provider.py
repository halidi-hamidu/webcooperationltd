# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Message Provider

Pure IMAP protocol implementation for message operations.
This module is provider-agnostic and handles only password-based IMAP authentication.
"""

import logging

from odoo.exceptions import UserError

from .client import IMAPClientWithAuth

_logger = logging.getLogger(__name__)


def create_imap_client_password(env, account):
    """
    Construct an authenticated IMAP client using username/password.

    This is a pure IMAP implementation that does NOT handle OAuth.
    For OAuth flows (Gmail, Outlook), use the application-level service.

    Args:
        env: Odoo environment
        account: Account record

    Returns:
        IMAPClientWithAuth: Authenticated IMAP client

    Raises:
        UserError: If configuration is invalid
        Exception: If authentication fails
    """
    server = account.mail_server_id
    if not server:
        raise UserError(env._("Incoming fetchmail.server is not configured"))

    host = server.server
    port = int(server.port or 993)
    use_ssl = bool(server.is_ssl)

    if not host:
        raise UserError(env._("IMAP host is not set on fetchmail.server"))

    client = IMAPClientWithAuth(
        host=host,
        port=port,
        ssl=use_ssl,
        use_uid=True,
        timeout=120,
    )

    user = (server.user or account.email or "").strip()
    pwd = getattr(server, "password", None)
    if not user or not pwd:
        client.logout()
        raise UserError(env._("IMAP username/password are not set on fetchmail.server"))

    try:
        client.login(user, pwd)
    except Exception as e:
        client.logout()
        raise Exception(f"IMAP password login failed: {e}")

    try:
        caps = client.capabilities() or []
        if (b"UTF8=ACCEPT" in caps) or ("UTF8=ACCEPT" in caps):
            client.enable("UTF8=ACCEPT")
    except Exception as e:
        _logger.debug("ignored error: %s", e)

    return client
