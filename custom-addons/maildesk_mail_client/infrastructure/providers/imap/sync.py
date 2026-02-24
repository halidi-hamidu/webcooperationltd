# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk IMAP sync provider wrapper.

Provides a small compatibility layer expected by `models/mailbox_account.py`.
Layer: infrastructure (provider adapter).
"""

from __future__ import annotations

from ...adapters.bus_notification_adapter import BusNotificationAdapter
from ....application.use_cases.sync_imap_folder import SyncImapFolderIncremental


class ImapSyncProvider:
    """Compatibility wrapper exposing the legacy `poll_incremental()` entrypoint."""

    def __init__(self, env, account):
        self._env = env
        self._account = account

    def poll_incremental(self) -> dict:
        notifier = BusNotificationAdapter(self._env)
        res = SyncImapFolderIncremental(self._env, notifier=notifier).execute(
            self._account.id
        )
        total = int(res.get("total_fetched") or 0)
        # Preserve poll_mail_accounts expectation: expose a boolean `changes`.
        return {**res, "changes": total > 0}
