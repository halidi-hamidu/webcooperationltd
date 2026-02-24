# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Gmail Authentication Provider
"""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
]


def is_gmail_account(account):
    """Check if account is a Gmail account."""
    if not account:
        return False
    return account.is_gmail


def gmail_build_service(account):
    """
    Build Gmail API service for account.

    Args:
        account: mailbox.account record

    Returns:
        Resource: Gmail API service resource
    """
    srv = account.mail_server_id.sudo()
    srv._generate_oauth2_string(srv.user, srv.google_gmail_refresh_token)
    srv.invalidate_recordset()

    token = srv.google_gmail_access_token
    refresh = srv.google_gmail_refresh_token

    Config = account.env["ir.config_parameter"].sudo()
    client_id = Config.get_param("google_gmail_client_id")
    client_secret = Config.get_param("google_gmail_client_secret")

    creds = Credentials(
        token=token,
        refresh_token=refresh,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GMAIL_SCOPES,
    )

    return build("gmail", "v1", credentials=creds, cache_discovery=False)
