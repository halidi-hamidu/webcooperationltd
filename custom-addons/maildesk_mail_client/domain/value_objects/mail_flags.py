# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Domain Value Object: Mail Flags

Represents the boolean state of email flags.
This is a domain concept, not an infrastructure detail.

ARCHITECTURAL RULES:
- MUST be immutable (frozen dataclass)
- MUST NOT contain Optional or None
- MUST represent complete, deterministic state
- Used across all layers for flag representation
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MailFlags:
    """
    Immutable value object representing email flags.

    Fields:
        is_read: Whether the message has been read (IMAP \\Seen flag)
        is_starred: Whether the message is starred (IMAP \\Flagged flag)

    Example:
        flags = MailFlags(is_read=True, is_starred=False)

    Rules:
        - No None values allowed
        - No Optional types
        - Immutable after creation
        - Represents complete state at a point in time
    """

    is_read: bool
    is_starred: bool

    def to_dict(self) -> dict:
        """
        Convert to dictionary for serialization.

        Returns:
            dict with is_read and is_starred keys
        """
        return {
            "is_read": self.is_read,
            "is_starred": self.is_starred,
        }

    @classmethod
    def from_imap_flags(cls, imap_flags: list) -> "MailFlags":
        """
        Create MailFlags from IMAP FLAGS response.

        Args:
            imap_flags: List of IMAP flag tokens (bytes or strings)

        Returns:
            MailFlags instance with computed boolean values

        Example:
            flags = MailFlags.from_imap_flags([b'\\Seen', b'\\Flagged'])
            # MailFlags(is_read=True, is_starred=True)
        """
        # Normalize flags to uppercase strings for comparison
        normalized = set()
        for flag in imap_flags or []:
            if isinstance(flag, bytes):
                normalized.add(flag.decode("utf-8", "ignore").upper())
            else:
                normalized.add(str(flag).upper())

        is_read = "\\SEEN" in normalized
        is_starred = "\\FLAGGED" in normalized

        return cls(is_read=is_read, is_starred=is_starred)
