# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Outlook Graph Auth.

Defines HTTP/JSON endpoints used by the MailDesk UI for Outlook Graph Auth.
Layer: odoo controllers.
"""

import json
import logging

from werkzeug.exceptions import Forbidden
from werkzeug.utils import redirect

from odoo import fields
from odoo import http
from odoo.http import request

from odoo.tools import consteq

from ..infrastructure.providers.outlook.auth_service import (
    BASIC_GRAPH_SCOPES,
    exchange_code,
    get_auth_url,
)
from ..infrastructure.providers.outlook.token_utils import (
    TOKEN_EXPIRY_SAFETY_SECONDS,
    compute_access_token_expiration_timestamp,
)

_logger = logging.getLogger(__name__)


class MicrosoftOutlookConfirmController(http.Controller):
    def _get_graph_scopes(self, provider):  # noqa: ARG002
        return BASIC_GRAPH_SCOPES

    @http.route("/maildesk/outlook/authorize", type="http", auth="user")
    def authorize(self, account_id, provider="maildesk_outlook", **kwargs):
        """
        Initiates the OAuth2 flow for Microsoft Graph.
        Delegates URL generation to the infrastructure service.
        """
        account = request.env["mailbox.account"].browse(int(account_id))
        if not account.exists():
            return request.not_found()

        # Callback URL (must match App Registration)
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        redirect_uri = f"{base_url}/microsoft_outlook/confirm"

        url = get_auth_url(
            request.env,
            account.id,
            redirect_uri,
            provider=provider,
            scopes=self._get_graph_scopes(provider),
        )
        return redirect(url)

    @http.route("/microsoft_outlook/confirm", type="http", auth="user")
    def microsoft_outlook_callback(
        self, code=None, state=None, error=None, error_description=None, **kwargs
    ):
        if error:
            return f"Microsoft Error: {error} - {error_description}"

        if not state or not code:
            raise Forbidden()

        try:
            data = json.loads(state)
        except Exception:  # noqa: BLE001
            _logger.exception("Failed to decode Outlook OAuth state")
            data = None

        if isinstance(data, dict) and data.get("provider"):
            provider = (data.get("provider") or "").strip()
            if not provider.startswith("maildesk_"):
                raise Forbidden()
            return self._handle_maildesk_outlook(code, data, provider)

        return self._handle_odoo_outlook(code, state, error_description)

    def _handle_maildesk_outlook(self, code, data, provider):
        """
        Handle MailDesk OAuth callback and persist tokens on mailbox.account.

        Strict isolation rules:
        - Tokens are stored ONLY on `mailbox.account.outlook_graph_*`.
        - Any legacy Odoo `microsoft_outlook_*` tokens on fetchmail.server are
          cleared to prevent standard Odoo IMAP/Outlook logic from taking over.
        - MailDesk sync cursors/backoff are reset to ensure stable resume.

        Args:
            code (str): OAuth authorization code.
            data (dict): Decoded state payload with `account_id` and `csrf`.
            provider (str): Provider identifier (must start with `maildesk_`).

        Returns:
            werkzeug.wrappers.Response: Redirect to the mailbox.account form.
        """
        account = (
            request.env["mailbox.account"].browse(int(data["account_id"])).exists()
        )
        if not account:
            raise Forbidden()

        if not consteq(
            data.get("csrf"), account.mail_server_id._get_outlook_csrf_token()
        ):
            raise Forbidden()

        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        redirect_uri = f"{base_url}/microsoft_outlook/confirm"

        scopes = self._get_graph_scopes(provider)
        if not scopes:
            raise Forbidden()

        tokens = exchange_code(request.env, code, redirect_uri, scopes=scopes)

        expires_in = int(tokens.get("expires_in") or 0)
        expiration_ts = (
            compute_access_token_expiration_timestamp(
                expires_in_seconds=expires_in,
                safety_seconds=TOKEN_EXPIRY_SAFETY_SECONDS,
            )
            if expires_in
            else False
        )

        # Sanitize account state on reconnect.
        account.sudo().write(
            {
                "outlook_graph_access_token": tokens["access_token"],
                "outlook_graph_refresh_token": tokens["refresh_token"],
                "outlook_graph_access_token_expiration": expiration_ts,
                "outlook_graph_auth_state": "ok",
                "outlook_graph_auth_error": False,
                "outlook_delta_tokens": {},
                "outlook_delta_link": False,
                "backoff_until": False,
                "maildesk_sync_requested_at": fields.Datetime.now(),
            }
        )

        # Strict isolation: clear legacy Odoo tokens so no fallback is possible.
        server = account.mail_server_id.sudo()
        if server and server.server_type == "outlook":
            server.write(
                {
                    "microsoft_outlook_refresh_token": False,
                    "microsoft_outlook_access_token": False,
                    "microsoft_outlook_access_token_expiration": False,
                }
            )

        return redirect(f"/web#id={account.id}&model=mailbox.account&view_type=form")

    def _handle_odoo_outlook(self, code, state, error_description):
        if not request.env.user.has_group("base.group_system"):
            raise Forbidden()

        try:
            state = json.loads(state)
            model_name = state["model"]
            rec_id = state["id"]
            csrf_token = state["csrf_token"]
        except Exception:
            raise Forbidden()

        model = request.env[model_name]
        record = model.browse(rec_id).exists()
        if not record:
            raise Forbidden()

        if not consteq(csrf_token, record._get_outlook_csrf_token()):
            raise Forbidden()

        refresh_token, access_token, expiration = record._fetch_outlook_refresh_token(
            code
        )

        record.write(
            {
                "microsoft_outlook_refresh_token": refresh_token,
                "microsoft_outlook_access_token": access_token,
                "microsoft_outlook_access_token_expiration": expiration,
            }
        )

        return redirect(f"/odoo/{model_name}/{rec_id}")
