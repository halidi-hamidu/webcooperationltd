# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Fetch Thread.

Implements the application-level use case for Fetch Thread.
Layer: application.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ...domain.contracts.threading_contract import ThreadingServiceDeps
from ...domain.services.threading import ThreadingParams, ThreadingService

# Alias Data Transfer Object for Use Case
FetchThreadParams = ThreadingParams
FetchThreadDeps = ThreadingServiceDeps


class FetchThread:
    """
    Application Use Case for fetching message threads.
    Orchestrates the request by delegating business logic to the Domain ThreadingService.
    Phase A: Structural preservation of the Use Case layer.
    """

    def __init__(self, deps: ThreadingServiceDeps):
        self._service = ThreadingService(deps)

    def execute(self, params: FetchThreadParams) -> List[Dict[str, Any]]:
        """
        Execute the thread fetch use case.
        Delegates pure domain logic to ThreadingService.
        """
        return self._service.execute(params)
