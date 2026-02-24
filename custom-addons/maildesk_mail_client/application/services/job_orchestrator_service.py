# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Job Orchestrator Service.

Provides application-layer services for Job Orchestrator Service.
Layer: application.
"""

import logging

_logger = logging.getLogger(__name__)


class JobOrchestratorService:
    """
    Stub application service for the job-based orchestrator.

    Stage 1 only: no sync logic, no side effects.
    """

    def __init__(self, env):
        self.env = env

    def poll_accounts(self, account_ids=None) -> dict:
        """
        Placeholder for job-based polling.
        """
        _logger.info(
            "JobOrchestratorService.poll_accounts invoked (stub), account_ids=%s",
            account_ids,
        )
        return {"ok": False, "changes": False, "reason": "not_implemented"}
