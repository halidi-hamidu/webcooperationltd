# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Message.

Defines domain concepts used by MailDesk (Message).
Layer: domain.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .attachment import Attachment


@dataclass(frozen=True)
class Message:
    """
    Canonical representation of an email message.
    Standardizes data shape across Gmail, Outlook, and IMAP providers.
    """

    # Identity
    id: str  # Opaque canonical message identifier (no provider semantics)
    thread_id: str  # Provider-specific Thread ID
    account_id: int  # Mailbox Account ID (Odoo)

    # RFC Headers (Normalized)
    message_header_id: str  # Message-ID header value
    in_reply_to: str  # In-Reply-To header value
    references: str  # References header value
    date: datetime  # Date header value

    # Envelope / Participants
    subject: str
    email_from: str  # Sender Email (e.g. bob@example.com)
    sender_display_name: str  # Sender Name (e.g. Bob Jones)
    to_display: str  # Decoded 'To' header (display string)
    cc_display: str  # Decoded 'Cc' header (display string)
    bcc_display: str  # Decoded 'Bcc' header (display string)

    # Content
    snippet: str  # Short preview text
    outgoing_id: str = ""  # X-MailDesk-Outgoing-ID (outgoing reconciliation)
    body_html: Optional[str] = None
    body_text: Optional[str] = None  # Plain text body

    # Flags & State
    is_read: bool = False
    is_starred: bool = False
    folder_ids: List[str] = field(default_factory=list)  # Abstract folder identifiers

    # Attachments
    has_attachments: bool = False
    attachments: List[Attachment] = field(default_factory=list)

    # Provider-Specific Metadata
    # Explicit storage for provider identifiers (e.g. imap_uid, change_key, etc.)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # UI Metadata (Overlay)
    avatar_html: Optional[str] = None
    avatar_partner_id: Optional[int] = None  # ID of matched res.partner
    partner_trusted: bool = False
    trusted_by_user_id: Optional[int] = None
