# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Auth Service.

Implements infrastructure integration for Auth Service (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

import json
import logging
from urllib.parse import urlencode

import requests
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BASIC_GRAPH_SCOPES = [
    "offline_access",
    "https://graph.microsoft.com/Mail.Read",
]


def get_auth_url(
    env, account_id, redirect_uri, *, provider="maildesk_outlook", scopes=None
):
    Config = env["ir.config_parameter"].sudo()
    client_id = Config.get_param("microsoft_outlook_client_id")
    tenant = Config.get_param("microsoft_outlook_tenant", "common")

    client_id = (client_id or "").strip()
    if not client_id:
        raise UserError(env._("Microsoft Outlook Client ID not configured."))

    account = env["mailbox.account"].browse(account_id).exists()
    if not account:
        raise UserError(env._("Mailbox account not found"))

    provider = (provider or "").strip() or "maildesk_outlook"
    state = json.dumps(
        {
            "provider": provider,
            "account_id": account.id,
            "csrf": account.mail_server_id._get_outlook_csrf_token(),
        }
    )

    scope = " ".join((scopes or BASIC_GRAPH_SCOPES) or [])
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": scope,
            "state": state,
            "prompt": "select_account",
        }
    )
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{query}"


def exchange_code(env, code, redirect_uri, *, scopes=None):
    """
    Exchanges the authorization code for tokens.

    Args:
        env: Odoo Environment
        code: Authorization code from callback
        redirect_uri: The callback URL used in the initial request

    Returns:
        dict: The JSON response from Microsoft containing access_token, refresh_token, etc.

    Raises:
        UserError: If client/secret is missing or exchange fails.
    """
    Config = env["ir.config_parameter"].sudo()
    client_id = Config.get_param("microsoft_outlook_client_id")
    client_secret = Config.get_param("microsoft_outlook_client_secret")
    tenant = Config.get_param("microsoft_outlook_tenant", "common")

    client_id = (client_id or "").strip()
    client_secret = (client_secret or "").strip()
    if not client_id or not client_secret:
        raise UserError(env._("Microsoft Outlook Client ID/Secret not configured."))

    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    scope = " ".join((scopes or BASIC_GRAPH_SCOPES) or [])
    payload = {
        "client_id": client_id,
        "scope": scope,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "client_secret": client_secret,
    }

    try:
        res = requests.post(token_url, data=payload, timeout=10)
        if not res.ok:
            _logger.error(
                "Microsoft token exchange failed: status=%s body=%s",
                res.status_code,
                res.text,
            )
            raise UserError(
                env._(
                    "Token Exchange Failed: HTTP %(code)s: %(body)s",
                    code=res.status_code,
                    body=res.text,
                )
            )
        return res.json()
    except Exception as e:
        _logger.exception("Failed to exchange code for token")
        raise UserError(env._("Token Exchange Failed: %(error)s", error=str(e)))
