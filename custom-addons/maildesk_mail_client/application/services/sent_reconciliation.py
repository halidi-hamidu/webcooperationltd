# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Sent-message reconciliation guards.

SSOT identity is `(provider, folder, uid)`. Threading/correlation fields like
`message_id`, `references`, or `outgoing_id` MUST NOT be used to collapse
distinct deliveries.

The only allowed overwrite-style mutation is confirming a *local_pending* row
created by SSOT-on-send when the provider's Sent copy is observed.
"""

from __future__ import annotations

from ...domain.services.normalization import norm_msgid


def is_same_delivery_for_sent_confirmation(
    *,
    folder_type: str,
    account_email: str,
    message_from: str,
    pending_message_id: str,
    server_message_id: str,
) -> bool:
    """
    Return True only when it is safe to reconcile a local_pending row in-place.

    Fail-closed rules:
    - Reconciliation is allowed only in a folder classified as `sent`
    - Sender must match the account email (protects against replies/forwards/lists)
    - Message-ID must match exactly after normalization
    """
    if (folder_type or "") != "sent":
        return False

    account_email_norm = (account_email or "").strip().lower()
    message_from_norm = (message_from or "").strip().lower()
    if not account_email_norm or not message_from_norm:
        return False
    if account_email_norm != message_from_norm:
        return False

    pending_mid = norm_msgid(pending_message_id)
    server_mid = norm_msgid(server_message_id)
    if not pending_mid or not server_mid:
        return False
    return pending_mid == server_mid
