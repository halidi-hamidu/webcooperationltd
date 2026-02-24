# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Shared helpers for normalizing mailbox folder and label identifiers.

MailDesk integrates multiple providers (IMAP, Gmail, Outlook). Each provider can
use different naming schemes (system labels, localized folder names, IMAP-style
paths). This module provides a single, shared normalization layer so that
mapping logic does not diverge across providers.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set


def normalize_folder_key(text: Optional[str]) -> str:
    """Normalize a folder/label name into a comparable key.

    Behavior:
    - lowercases and trims
    - collapses internal whitespace
    - strips a leading `[Gmail]/` prefix when present
    """
    if not text:
        return ""
    t = " ".join(str(text).strip().lower().split())
    if t.startswith("[gmail]/"):
        t = t.replace("[gmail]/", "", 1).strip()
    return t


def label_synonyms() -> Dict[str, List[str]]:
    """Return canonical label synonyms used for folder/label mapping.

    Contract:
    - Each list contains the canonical key as its first element.
    - All values MUST be normalized with :func:`normalize_folder_key`.
    """
    return {
        "inbox": ["inbox"],
        "sent": ["sent", "sent mail", "sent items"],
        "draft": ["draft", "drafts"],
        "trash": ["trash", "bin", "deleted", "deleted messages"],
        "spam": ["spam", "junk"],
        "all mail": ["all mail", "allmail", "all_mail", "archive"],
        "starred": ["starred", "flagged"],
        "important": ["important"],
    }


def expand_synonyms(keys: Iterable[str]) -> Set[str]:
    """Expand a set of normalized keys using :func:`label_synonyms`.

    Args:
        keys: Iterable of already-normalized keys.

    Returns:
        A superset of `keys` containing all acceptable synonym keys.
    """
    acceptable: Set[str] = {k for k in keys if k}
    synonyms = label_synonyms()
    for key in list(acceptable):
        for canon, names in synonyms.items():
            if key == canon or key in names:
                acceptable.update(names)
    return acceptable


def folder_type_keys(folder_type: str) -> Set[str]:
    """Map an Odoo `mailbox.folder.folder_type` into normalized lookup keys."""
    ft = normalize_folder_key(folder_type)
    if not ft:
        return set()
    if ft == "archive":
        return {"all mail", "allmail", "all_mail", "archive"}
    if ft == "drafts":
        return {"draft", "drafts"}
    if ft == "sent":
        return {"sent", "sent mail", "sent items"}
    if ft == "trash":
        return {"trash", "bin", "deleted", "deleted messages"}
    if ft == "spam":
        return {"spam", "junk"}
    if ft == "inbox":
        return {"inbox"}
    if ft == "starred":
        return {"starred", "flagged"}
    if ft == "important":
        return {"important"}
    return {ft}


def keys_from_text(text: Optional[str]) -> Set[str]:
    """Return a singleton key set extracted from `text` (or an empty set)."""
    key = normalize_folder_key(text)
    return {key} if key else set()


def is_all_mail_folder(text: Optional[str]) -> bool:
    """Return True when `text` identifies Gmail's 'All Mail' folder/label."""
    return normalize_folder_key(text) in {"all mail", "allmail", "all_mail", "archive"}


def record_has_field(record: Any, field_name: str) -> bool:
    """Return True when `record` is an Odoo recordset that exposes `field_name`."""
    try:
        return field_name in (record._fields if record else {})
    except (AttributeError, TypeError):
        return False
