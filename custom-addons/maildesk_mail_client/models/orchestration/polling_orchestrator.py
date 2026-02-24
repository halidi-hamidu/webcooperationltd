# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Polling Orchestrator.

Defines Odoo ORM models and server-side APIs for Polling Orchestrator.
Layer: odoo models.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class PollingOrchestrator(models.AbstractModel):
    _name = "maildesk.polling_orchestrator"
    _description = "MailDesk Polling Orchestrator"

    @api.model
    def run_cron(self):
        """
        Main Cron Entry Point.
        Decides WHEN sync should happen.
        """
        _logger.info("PollingOrchestrator: cron triggered")
        self.env["maildesk.sync_orchestrator"].sync_all()

    @api.model
    def heartbeat(self):
        """
        Called by UI periodic polling (e.g. every minute).
        Triggers a lightweight sync or status check.
        """
        # For now, we can trigger a sync cycle for the current user's accounts
        # This mirrors typical "fetch now" behavior in UI
        user_accounts = self.env["mailbox.account"].search(
            [("create_uid", "=", self.env.uid), ("active", "=", True)]
        )
        for acc in user_accounts:
            self.env["maildesk.sync_orchestrator"].sync_account(acc.id)
        return True
