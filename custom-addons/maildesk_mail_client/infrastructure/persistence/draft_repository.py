# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Draft Repository: Encapsulates all ORM access to maildesk.draft.
Provides clean interface for draft lifecycle operations (create, read, update, delete).
"""


class DraftRepository:
    """Repository for draft persistence operations."""

    def __init__(self, env):
        self._env = env
        # Use sudo to bypass access checks; in Odoo 19 `sudo()` toggles superuser
        # mode without changing the current user.
        self._draft_model = env["maildesk.draft"].sudo()

    def create(self, vals):  # pylint: disable=method-required-super
        """Create a new draft."""
        vals = dict(vals or {})
        vals.setdefault("user_id", self._env.uid)
        return self._draft_model.create(vals)

    def browse(self, draft_id):
        """Browse draft by ID."""
        return self._draft_model.browse(int(draft_id))

    def update(self, draft, vals):
        """Update an existing draft."""
        vals = dict(vals or {})
        # Heal legacy drafts that were accidentally created under the superuser
        # (e.g. due to older `.sudo()` semantics). Keep ownership stable for
        # normal drafts.
        if getattr(getattr(draft, "user_id", None), "id", None) == 1:
            vals.setdefault("user_id", self._env.uid)
        draft.write(vals)

    def delete(self, draft):
        """Delete a draft."""
        draft.unlink()

    def exists(self, draft):
        """Check if draft exists."""
        return bool(draft and draft.exists())

    def search(self, domain, limit=None):
        """Search for drafts."""
        return self._draft_model.search(domain, limit=limit)
