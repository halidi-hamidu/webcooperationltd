# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Sent Append Policy: Determines if manual IMAP append to Sent folder is needed.

This is a pure decision helper that checks provider type and server configuration.
Gmail and Outlook auto-append sent messages; IMAP requires manual append.
"""


def need_manual_sent_append(account) -> bool:
    """
    Determine if manual IMAP append to Sent folder is needed.

    Gmail and Outlook automatically append sent messages to the Sent folder,
    so manual IMAP append is not needed. For IMAP accounts, manual append is required.

    Args:
        account: mailbox.account record

    Returns:
        True if manual append needed (IMAP), False otherwise (Gmail/Outlook)
    """
    # Feature flag: only append when explicitly enabled on the account.
    if not getattr(account, "append_sent_to_imap", False):
        return False

    server = account.mail_server_id
    if not server:
        return False

    st = (server.server_type or "").lower().strip()
    host = (server.server or "").lower().strip()

    # Gmail and Outlook handle sent folder automatically
    if st in ("gmail", "outlook"):
        return False

    # Check if it's Gmail by hostname
    if "gmail" in host or "googlemail" in host:
        return False

    # Check if it's Outlook by hostname
    if "outlook" in host or "office365" in host or "hotmail" in host:
        return False

    # Default: IMAP requires manual append
    return True
