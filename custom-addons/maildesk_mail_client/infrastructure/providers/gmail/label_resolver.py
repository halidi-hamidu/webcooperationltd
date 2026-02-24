# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Gmail label resolution helpers.

MailDesk stores Gmail folders as IMAP-style names (e.g. `[Gmail]/Sent Mail`,
`[Gmail]/Enviados`) but interacts with Gmail via the Gmail API, which identifies
folders by *label IDs* and exposes system labels with stable names like `SENT`.

This module resolves an Odoo `mailbox.folder` record to a Gmail label ID in a
locale-robust way by combining:
- folder metadata (`folder.folder_type`, `folder.gmail_label_id`)
- folder display fields (`folder.name`, `folder.imap_name`)
- Gmail API labels list (system + user labels)
"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from ...utils.folder_keys import (
    expand_synonyms,
    folder_type_keys,
    keys_from_text,
    normalize_folder_key,
    record_has_field,
)


def resolve_gmail_label(
    service, folder, *, folder_name: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a Gmail label ID for a MailDesk folder.

    Args:
        service: Gmail API service as built by `gmail_build_service(account)`.
        folder: Odoo `mailbox.folder` record.
        folder_name: Optional explicit folder name to consider in addition to
            `folder.name` and `folder.imap_name`.

    Returns:
        Tuple `(label_id, label_name)` where `label_id` is the Gmail label id as
        a string (or `None` if not found) and `label_name` is the Gmail label
        display name as returned by the API when found.

    Behavior:
        - If the folder already stores `gmail_label_id`, it is trusted and
          returned without listing labels.
        - If the IMAP folder name is localized (e.g. `[Gmail]/Enviados`), we
          rely on `folder.folder_type` to map it to a canonical system label
          (e.g. `SENT`) and match by name.
    """
    if record_has_field(folder, "gmail_label_id") and folder.gmail_label_id:
        return str(folder.gmail_label_id), None

    labels = _list_labels(service)
    if not labels:
        return None, None

    keys: Set[str] = set()
    keys |= keys_from_text(getattr(folder, "name", None))
    keys |= keys_from_text(getattr(folder, "imap_name", None))
    keys |= keys_from_text(folder_name)

    folder_type = getattr(folder, "folder_type", None)
    keys |= folder_type_keys(folder_type or "")

    if not keys:
        return None, None

    acceptable = expand_synonyms(keys)
    for label in labels:
        name = (label.get("name") or "").strip()
        key = normalize_folder_key(name)
        if key in acceptable:
            return str(label.get("id") or ""), name

    return None, None


def _list_labels(service) -> List[dict]:
    try:
        resp = service.users().labels().list(userId="me").execute()
    except Exception:
        return []
    return list(resp.get("labels") or [])
