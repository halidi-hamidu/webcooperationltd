# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Client Factory.

Implements infrastructure integration for Client Factory (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

import json
import logging
import time
from typing import Optional, Tuple

import msal
import requests
from odoo.exceptions import UserError
from psycopg2.errors import SerializationFailure

from .token_utils import (
    TOKEN_EXPIRY_SAFETY_SECONDS,
    compute_access_token_expiration_timestamp,
)

_logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_MSAL_SCOPES = ["https://graph.microsoft.com/Mail.Read"]

TOKEN_TEST_TIMEOUT_SECONDS = 5


def is_outlook_account(account):
    srv = account.mail_server_id.sudo()
    return bool(srv) and (srv.server_type or "").lower() == "outlook"


def get_outlook_access_token(account):
    server = account.mail_server_id.sudo()
    server._generate_outlook_oauth2_string(account.email or server.user)
    return server.microsoft_outlook_access_token


def _is_invalid_client_secret_error(result: dict) -> bool:
    """
    Detect Azure AD invalid client secret errors in MSAL token responses.

    Args:
        result (dict): MSAL result dict returned from token acquisition calls.

    Returns:
        bool: True if the result indicates an invalid client secret (AADSTS7000215).
    """
    desc = str(result.get("error_description") or "").lower()
    return "aadsts7000215" in desc or "invalid client secret" in desc


def _persist_outlook_graph_auth_state(
    *,
    account,
    state: str,
    error_message: Optional[str] = None,
) -> None:
    """
    Persist Outlook Graph auth state on a MailDesk mailbox.account.

    Args:
        account: `mailbox.account` record (sudo is applied internally).
        state (str): One of `ok`, `reauth_required`, `auth_invalid`.
        error_message (Optional[str]): Human-readable error for diagnostics.

    Side effects:
        Writes to `mailbox.account` fields:
        - `outlook_graph_auth_state`
        - `outlook_graph_auth_error`
    """
    vals = {
        "outlook_graph_auth_state": str(state or "ok"),
        "outlook_graph_auth_error": (error_message or "").strip() or False,
    }
    try:
        with account.env.cr.savepoint():
            account.sudo().write(vals)
    except Exception:
        _logger.warning(
            "Failed to persist Outlook Graph auth state for account %s", account.id
        )


def get_outlook_client(
    env, account
) -> Tuple[Optional[requests.Session], Optional[str]]:
    """
    Build an authenticated requests Session for Outlook Graph API.
    Handles token refresh if necessary and updates the database.

    Returns:
        (requests.Session, str): Session object and Graph Base URL.
        Returns (None, None) if not an Outlook account.
    """
    if not account or not account.id:
        return None, None

    server = account.mail_server_id.sudo()
    if not server or (server.server_type or "").lower() != "outlook":
        return None, None

    Config = env["ir.config_parameter"].sudo()
    client_id = (Config.get_param("microsoft_outlook_client_id") or "").strip()
    client_secret = (Config.get_param("microsoft_outlook_client_secret") or "").strip()
    tenant = (Config.get_param("microsoft_outlook_tenant", "common") or "").strip()

    if not (client_id and client_secret):
        raise UserError(
            env._(
                "Outlook Graph is not configured. Please set Client Id and Client Secret."
            )
        )

    # Strict isolation:
    # MailDesk mailbox.account must never rely on Odoo's `microsoft_outlook` mixin
    # tokens stored on fetchmail.server. Only mailbox.account.outlook_graph_* is used.
    graph_rt = (account.outlook_graph_refresh_token or "").strip()
    graph_at = (account.outlook_graph_access_token or "").strip()

    if (account.outlook_graph_auth_state or "") == "auth_invalid":
        raise UserError(
            env._(
                "Microsoft Graph authentication is disabled for this account because "
                "the OAuth client secret is invalid or misconfigured. Please fix the "
                "Outlook Client Secret in Settings and reconnect this mailbox."
            )
        )

    if not graph_rt:
        _persist_outlook_graph_auth_state(
            account=account,
            state="reauth_required",
            error_message="Missing refresh token (offline_access consent likely missing).",
        )
        raise UserError(
            env._(
                "Microsoft Graph is not connected for this mailbox. Please click "
                "'Connect Microsoft Graph (OAuth)' to authorize offline access."
            )
        )

    def _make_session(access_token: str) -> requests.Session:
        sess = requests.Session()
        sess.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Prefer": 'IdType="ImmutableId"',
            }
        )
        return sess

    # Fast-path: if we have a not-yet-expired token timestamp, avoid a probe call.
    now_ts = int(time.time())
    exp_raw = int(account.outlook_graph_access_token_expiration or 0)
    if graph_at and exp_raw and exp_raw > now_ts:
        return _make_session(graph_at), GRAPH_BASE_URL

    # Probe token validity; only refresh on 401.
    if graph_at:
        sess = _make_session(graph_at)
        try:
            r = sess.get(
                f"{GRAPH_BASE_URL}/me?$select=id", timeout=TOKEN_TEST_TIMEOUT_SECONDS
            )
            if r.status_code != 401:
                return sess, GRAPH_BASE_URL
            _logger.info("Outlook Graph: access token expired (401), refreshing...")
        except Exception as e:
            _logger.warning("Outlook Graph: token probe failed (%s), refreshing...", e)

    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant}",
    )
    # MSAL forbids passing reserved scopes (openid/profile/offline_access) and
    # will add them as needed for interactive flows. We therefore only request
    # Graph resource scopes here.
    result = app.acquire_token_by_refresh_token(graph_rt, scopes=GRAPH_MSAL_SCOPES)

    if "access_token" not in result:
        err_desc = (result.get("error_description") or json.dumps(result)).strip()
        err_code = (result.get("error") or "").lower()

        if _is_invalid_client_secret_error(result):
            _persist_outlook_graph_auth_state(
                account=account,
                state="auth_invalid",
                error_message=err_desc,
            )
            raise UserError(
                env._(
                    "Microsoft Graph authentication failed because the configured "
                    "Client Secret is invalid (AADSTS7000215). Please update the "
                    "Client Secret in Settings; sync is paused to prevent retry storms."
                )
            )

        if (
            "invalid_grant" in err_code
            or "interaction_required" in err_code
            or "consent" in err_desc.lower()
            or "aadsts65001" in err_desc.lower()
        ):
            _persist_outlook_graph_auth_state(
                account=account,
                state="reauth_required",
                error_message=err_desc,
            )
            raise UserError(
                env._(
                    "Microsoft Graph session expired or requires consent. Please reconnect "
                    "this mailbox in the account settings."
                )
            )

        _persist_outlook_graph_auth_state(
            account=account,
            state="reauth_required",
            error_message=err_desc,
        )
        raise UserError(
            env._(
                "An error occurred when contacting Microsoft Graph: %(err)s",
                err=err_desc,
            )
        )

    access_token = (result.get("access_token") or "").strip()
    refresh_token = (result.get("refresh_token") or graph_rt).strip()
    expires_in = int(result.get("expires_in") or 0)

    vals = {
        "outlook_graph_access_token": access_token,
        "outlook_graph_refresh_token": refresh_token,
        "outlook_graph_auth_state": "ok",
        "outlook_graph_auth_error": False,
    }
    if expires_in:
        vals["outlook_graph_access_token_expiration"] = (
            compute_access_token_expiration_timestamp(
                expires_in_seconds=expires_in,
                safety_seconds=TOKEN_EXPIRY_SAFETY_SECONDS,
            )
        )

    try:
        with env.cr.savepoint():
            account.sudo().write(vals)
    except SerializationFailure as e:
        _logger.warning(
            "Concurrent update on mailbox.account %s when saving Graph tokens: %s",
            account.id,
            e,
        )
    except Exception as e:
        _logger.warning(
            "Failed to save refreshed Graph token for account %s: %s", account.id, e
        )

    return _make_session(access_token), GRAPH_BASE_URL
