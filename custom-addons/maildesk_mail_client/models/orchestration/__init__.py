# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Init.

Exports subpackages to register MailDesk components in Odoo.
Layer: odoo models.
"""

# ruff: noqa: F401
from . import bus_orchestrator, polling_orchestrator, sync_orchestrator
