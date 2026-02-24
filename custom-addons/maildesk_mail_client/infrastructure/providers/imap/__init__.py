# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Infrastructure

Connection pooling, client wrappers, search builders, list fetching, and client factory for IMAP provider.
"""

from .client import IMAPClientWithAuth, MailDeskIMAPPool
from .list_provider import fetch_list_records_parallel
from .message_provider import create_imap_client_password
from .mime_analyzer import has_attachments_from_bodystructure
from .pool import get_pool
from .search_builder import build_search_criteria, criteria_key, fast_search_uids

__all__ = [
    "get_pool",
    "IMAPClientWithAuth",
    "MailDeskIMAPPool",
    "criteria_key",
    "build_search_criteria",
    "fast_search_uids",
    "fetch_list_records_parallel",
    "create_imap_client_password",
    "has_attachments_from_bodystructure",
]
