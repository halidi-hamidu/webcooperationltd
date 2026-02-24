# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Capabilities: Infrastructure service for handling IMAP capabilities.
"""

import logging

from .client_factory import build_imap_client

_logger = logging.getLogger(__name__)


def ensure_capabilities(client, account, folder_name, env):
    """
    Ensure IMAP capabilities are fetched, retrying with folder selection if needed.
    """

    try:
        caps = client.capabilities() or set()
    except Exception:
        try:
            client.logout()
        except Exception as e:
            _logger.debug("ignored error: %s", e)

        # Retry with a fresh client and folder selection
        client = build_imap_client(env, account)
        client.select_folder(folder_name, readonly=True)
        caps = client.capabilities() or set()

    caps = {(c.decode() if isinstance(c, bytes) else c).upper() for c in caps}
    return client, caps
