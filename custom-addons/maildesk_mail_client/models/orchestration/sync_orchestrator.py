# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Sync Orchestrator.

Defines Odoo ORM models and server-side APIs for Sync Orchestrator.
Layer: odoo models.
"""

import logging

from odoo import api, fields, models

from ...application.use_cases import ScanImapFolders, SyncImapFolderIncremental
from ...infrastructure.adapters.bus_notification_adapter import BusNotificationAdapter

_logger = logging.getLogger(__name__)


class SyncOrchestrator(models.AbstractModel):
    _name = "maildesk.sync_orchestrator"
    _description = "MailDesk Sync Orchestrator"

    @api.model
    def sync_all(self):
        """
        Orchestrate sync for all active maildesk accounts.
        Typically called by Cron.
        """
        now = fields.Datetime.now()
        accounts = self.env["mailbox.account"].search(
            [
                ("active", "=", True),
                "|",
                ("backoff_until", "=", False),
                ("backoff_until", "<=", now),
            ]
        )
        for acc in accounts:
            self.sync_account(acc.id)

    @api.model
    def sync_account(self, account_id):
        """
        Orchestrate sync for a specific account.
        Dispatches to the valid provider implementation.
        """
        account = self.env["mailbox.account"].browse(account_id)
        if not account.exists():
            return
        if account.backoff_until and account.backoff_until > fields.Datetime.now():
            return

        provider = "imap"
        if account.is_gmail:
            provider = "gmail"
        elif account.is_outlook:
            provider = "outlook"

        # This orchestrator is IMAP-only. Gmail/Outlook have dedicated cron entrypoints
        # (History/Delta) and must not fall back to IMAP auth.
        if provider != "imap":
            return

        # Skip misconfigured IMAP accounts (common in demo/test DBs) to avoid noisy
        # DNS/auth errors during unrelated cron runs.
        server = account.mail_server_id
        if not server or not (server.server or "").strip():
            return
        _logger.info(
            "SyncOrchestrator: triggering sync for %s (%s)", account.name, provider
        )

        try:
            self._dispatch_imap(account)
        except Exception as e:
            if getattr(e, "pgcode", None) == "40001":
                raise
            _logger.exception("SyncOrchestrator: failed to sync account %s", account_id)

    def _dispatch_gmail(self, account):
        # TODO: Link to actual GmailSyncWorker or legacy method
        # Currently delegating to IMAP/Generic flow as fallback
        return

    def _dispatch_outlook(self, account):
        # TODO: Link to actual Outlook sync logic
        return

    def _dispatch_imap(self, account):
        """
        Two-Phase IMAP Sync:
        1. Maintain folder structure (discovery)
        2. Phase 1: Scan all folders for changes (cheap STATUS)
        3. Phase 2: Targeted sync of dirty folders
        """
        # 0. Folder Structure Sync (Discovery)
        # Keeps local folder tree in sync with server
        try:
            with self.env.cr.savepoint():
                account.sync_imap_folders()
        except Exception as e:
            _logger.error("Folder structure sync failed for %s: %s", account.id, e)

        # 1. Phase 1: Scan (Cheap)
        try:
            with self.env.cr.savepoint():
                ScanImapFolders(self.env).execute(account)
        except Exception as e:
            if getattr(e, "pgcode", None) == "40001":
                raise
            _logger.error("Phase 1 Scan failed for %s: %s", account.id, e)

        # 2. Phase 2: Multi-Folder Sync (cost-limited internally)
        # Use case handles folder batching and UID budget across folders
        try:
            with self.env.cr.savepoint():
                notifier = BusNotificationAdapter(self.env)
                use_case = SyncImapFolderIncremental(self.env, notifier=notifier)
                use_case.execute(account.id)
        except Exception as e:
            if getattr(e, "pgcode", None) == "40001":
                raise
            _logger.error("Phase 2 Sync failed for %s: %s", account.id, e)
