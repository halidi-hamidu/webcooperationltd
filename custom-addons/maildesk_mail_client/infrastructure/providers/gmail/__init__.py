# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Gmail Infrastructure

Gmail API integration for message fetching and management.
"""

from .list_provider import (
    gmail_fetch_meta_batch,
    gmail_query_from_filters,
    gmail_unread_counts,
)
from .message_provider import gmail_get_message_full
from .thread_provider import gmail_get_thread_full

__all__ = [
    "gmail_fetch_meta_batch",
    "gmail_query_from_filters",
    "gmail_unread_counts",
    "gmail_get_thread_full",
    "gmail_get_message_full",
]
