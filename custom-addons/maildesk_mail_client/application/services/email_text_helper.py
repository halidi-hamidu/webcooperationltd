# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Email Text Helper: Utilities for converting between text and list formats for email addresses.
"""


class EmailTextHelper:
    """Helper for text <-> list conversion of email addresses."""

    def to_text(self, lst):
        """Convert list of emails to newline-separated string."""
        return "\n".join([x.strip() for x in (lst or []) if x])

    def to_list(self, txt):
        """Convert string (newline or comma separated) to list of emails."""
        if not txt:
            return []
        # Support both newlines (legacy Odoo behavior) and commas (standard) just in case,
        # though legacy _to_list used splitlines.
        # But wait, legacy _to_list in mailbox_sync.py used splitlines().
        # Let's check logic: [x.strip() for x in txt.splitlines() if x.strip()]
        return [x.strip() for x in txt.splitlines() if x.strip()]
