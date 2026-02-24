# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Persistence layer exports."""

from .draft_repository import DraftRepository
from .message_index_repository import MessageIndexRepository

__all__ = ["DraftRepository", "MessageIndexRepository"]
