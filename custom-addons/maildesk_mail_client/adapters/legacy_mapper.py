# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Legacy Mapper.

Bridges MailDesk application logic to Odoo/external interfaces for Legacy Mapper.
Layer: interface adapters.
"""

from typing import Any, Dict

from ..domain.contracts import Message


def message_to_legacy_dict(msg: Message) -> Dict[str, Any]:
    """
    Temporary legacy boundary — will be removed once use-cases consume contracts directly.
    Maps canonical Message contract to legacy dictionary format expected by mailbox_sync.
    """
    res = {
        "id": msg.id,  # Opaque canonical identifier
        "subject": msg.subject,
        "preview": msg.snippet,
        "from_addr": msg.email_from,
        "to_addrs": msg.to_display,
        "cc_addrs": msg.cc_display,
        "date": msg.date,
        "message_id": msg.message_header_id,
        "in_reply_to": msg.in_reply_to,
        "references_hdr": msg.references,
        "thread_id": msg.thread_id,
        # Flags - critical for UI display
        "is_read": msg.is_read,
        "is_starred": msg.is_starred,
        "has_attachments": msg.has_attachments,
        "sender_display_name": msg.sender_display_name,
    }

    # Explicit IMAP UID from metadata (no guessing)
    imap_uid = msg.metadata.get("imap_uid")
    if imap_uid is not None:
        res["uid"] = imap_uid

    return res
