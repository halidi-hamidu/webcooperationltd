# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Connection Pool Manager

Global connection pool registry and factory function.
"""

import threading

from .client import MailDeskIMAPPool

# Global pool registry
_POOLS = {}
_POOLS_LOCK = threading.Lock()


def get_pool(account):
    """
    Return a shared IMAP connection pool for the given account, creating one
    lazily under a global lock when none exists. Pools are keyed by account ID
    so concurrent users reuse the same small set of authenticated IMAP clients
    rather than repeatedly logging in. This reduces connection overhead while
    isolating per-account credentials.
    """
    key = account.id
    with _POOLS_LOCK:
        pool = _POOLS.get(key)
        if not pool:
            pool = MailDeskIMAPPool(account, size=4)
            _POOLS[key] = pool
        return pool
