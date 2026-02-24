# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Application Service: IMAP Client Service

Responsible for provider selection and authenticated IMAP client creation.
This is the ONLY place where cross-provider orchestration happens.
"""

import logging

from odoo.exceptions import UserError

from ...infrastructure.providers.imap.client import IMAPClientWithAuth

_logger = logging.getLogger(__name__)


def build_authenticated_imap_client(env, account):
    """
    Build and return an authenticated IMAP client for the given account.

    This function performs provider selection (Gmail OAuth, Outlook OAuth, or password)
    and returns a ready-to-use IMAP client.

    Args:
        env: Odoo environment
        account: mailbox.account record

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

    # Provider selection: Gmail OAuth
    if account.is_gmail:
        return _authenticate_gmail(env, account, server, client)

    # Provider selection: Outlook OAuth
    if account.is_outlook:
        return _authenticate_outlook(env, account, server, client)

    # Default: password-based IMAP
    return _authenticate_password(env, account, server, client)


def _authenticate_gmail(env, account, server, client):
    """Authenticate IMAP client using Gmail OAuth2."""
    try:
        # Force token refresh
        if hasattr(server, "_generate_oauth2_string"):
            server._generate_oauth2_string(
                server.user, server.google_gmail_refresh_token
            )
            server.invalidate_recordset()
    except Exception as e:
        _logger.warning("Failed to refresh Gmail OAuth token: %s", e)

    access_token = getattr(server, "google_gmail_access_token", None)
    username = (server.user or account.email or "").strip()
    if not access_token or not username:
        raise UserError(
            env._("Gmail OAuth2: missing access token or username (server.user).")
        )

    try:
        client.oauth2_login(username, access_token)
    except Exception as e:
        client.logout()
        raise Exception(f"Gmail XOAUTH2 login failed: {e}")

    _enable_utf8_if_available(client)
    return client


def _authenticate_outlook(env, account, server, client):
    """Authenticate IMAP client using Outlook OAuth2."""
    username = (server.user or account.email or "").strip()
    if not username:
        client.logout()
        raise UserError(
            env._("Outlook OAuth2: missing username (fetchmail.server.user).")
        )

    if not hasattr(server, "_generate_outlook_oauth2_string"):
        client.logout()
        raise UserError(
            env._(
                "Outlook OAuth2: server does not provide _generate_outlook_oauth2_string()."
            )
        )

    try:
        server._generate_outlook_oauth2_string(username)
    except Exception as e:
        client.logout()
        raise Exception(f"Outlook OAuth2: could not (re)fetch access token: {e}")

    access_token = getattr(server, "microsoft_outlook_access_token", None)
    if not access_token:
        client.logout()
        raise UserError(
            env._("Outlook OAuth2: access token not available after refresh.")
        )

    try:
        client.oauth2_login(username, access_token)
    except Exception as e:
        client.logout()
        raise Exception(f"Outlook XOAUTH2 login failed: {e}")

    _enable_utf8_if_available(client)
    return client


def _authenticate_password(env, account, server, client):
    """Authenticate IMAP client using username/password."""
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

    _enable_utf8_if_available(client)
    return client


def _enable_utf8_if_available(client):
    """Enable UTF8 support if advertised by the IMAP server."""
    try:
        caps = client.capabilities() or []
        if (b"UTF8=ACCEPT" in caps) or ("UTF8=ACCEPT" in caps):
            client.enable("UTF8=ACCEPT")
    except Exception as e:
        _logger.debug("ignored error: %s", e)
