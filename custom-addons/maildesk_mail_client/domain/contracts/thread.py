# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Thread.

Defines domain concepts used by MailDesk (Thread).
Layer: domain.
"""

from dataclasses import dataclass, field
from typing import List

from .message import Message


@dataclass(frozen=True)
class Thread:
    """
    Canonical representation of an email thread.
    A thread aggregates messages that belong to the same conversation.
    """

    id: str  # Provider-specific Thread ID
    account_id: int  # Mailbox Account ID (Odoo)
    subject: str  # Representative subject for the thread

    messages: List[Message] = field(default_factory=list)
