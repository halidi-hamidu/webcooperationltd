# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Errors.

Provides application-layer services for Errors.
Layer: application.
"""


class MailDeskError(Exception):
    """Base error for MailDesk application invariants and provider failures."""


class MailDeskInvariantError(MailDeskError):
    """Raised when required SSOT/cache invariants are violated."""


class MailDeskProviderFetchError(MailDeskError):
    """Raised when provider fetch is required but fails or returns unusable data."""
