# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Client Factory (DEPRECATED - Use application/services/imap_client_service.py)

This module is kept for backward compatibility but delegates to the application service.
New code should import from application.services.imap_client_service directly.
"""

from ...application.services.imap_client_service import build_authenticated_imap_client


def build_imap_client(env, account):
    """
    DEPRECATED: Use application.services.imap_client_service.build_authenticated_imap_client

    Delegates to the application-level service which handles provider selection.
    """
    return build_authenticated_imap_client(env, account)
