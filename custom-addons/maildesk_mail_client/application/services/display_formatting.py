# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Display Formatting Service

SINGLE SOURCE OF TRUTH for all sender/recipient display name logic.

Clean Architecture:
- Lives in APPLICATION SERVICE layer
- NO ORM dependencies
- NO provider-specific logic
- Pure functions for display formatting
"""


def compute_sender_display_name(
    from_addr: str,
    raw_sender_name: str = None,
    partner_name: str = None,
) -> str:
    """
    Compute sender display name with consistent priority rules.

    CANONICAL METHOD - used by:
    - Bootstrap (writes to message_index.sender_display_name)
    - Backfill (writes to message_index.sender_display_name)
    - List view (reads from message_index.sender_display_name)
    - Open message (reads from message_index.sender_display_name)

    Priority:
    1. raw_sender_name (from MIME headers, already MIME-decoded)
    2. partner_name (from res.partner if matched)
    3. email address part before @ (fallback)

    Args:
        from_addr: Email address (e.g., "bob@example.com")
        raw_sender_name: Decoded name from email (e.g., "Bob Jones")
        partner_name: Name from matched partner

    Returns:
        Display name (e.g., "Bob Jones" or "bob@example.com")

    Examples:
        >>> compute_sender_display_name("bob@company.com", "Bob Jones")
        "Bob Jones"

        >>> compute_sender_display_name("bob@company.com", partner_name="Robert J.")
        "Robert J."

        >>> compute_sender_display_name("bob@company.com")
        "bob@company.com"
    """
    # Priority 1: Raw sender name from email headers
    if raw_sender_name and raw_sender_name.strip():
        return raw_sender_name.strip()

    # Priority 2: Partner name if available
    if partner_name and partner_name.strip():
        return partner_name.strip()

    # Priority 3: Email address fallback
    if from_addr:
        return from_addr.strip()

    return "(Unknown Sender)"


def compute_display_contact(
    folder_type: str,
    from_addr: str,
    to_addrs: str,
    sender_display_name: str,
) -> tuple:
    """
    Compute display contact based on folder type.

    SENT folders: show RECIPIENT (who received the email)
    Other folders: show SENDER (who sent the email)

    This ensures:
    - INBOX shows who messaged you
    - SENT shows who you messaged

    Args:
        folder_type: "sent", "inbox", "drafts", etc.
        from_addr: Sender email
        to_addrs: Comma-separated recipient emails
        sender_display_name: Pre-computed sender display name

    Returns:
        (contact_email, contact_display_name) tuple

    Examples:
        >>> compute_display_contact("inbox", "bob@ex.com", "you@ex.com", "Bob")
        ("bob@ex.com", "Bob")

        >>> compute_display_contact("sent", "you@ex.com", "alice@ex.com, bob@ex.com", "You")
        ("alice@ex.com", "alice@ex.com")
    """
    if folder_type == "sent":
        # For SENT folder: show primary recipient
        primary_recipient = _parse_first_recipient(to_addrs)
        if primary_recipient:
            # For recipients, we don't have a pre-computed name
            # so we return the email as both contact and display name
            # (UI can enhance with partner info if available)
            return (primary_recipient, primary_recipient)
        # Fallback if no recipients
        return ("", "(No Recipients)")
    else:
        # For INBOX and other folders: show sender
        return (from_addr, sender_display_name)


def _parse_first_recipient(to_addrs: str) -> str:
    """
    Extract first recipient email from comma-separated list.

    Args:
        to_addrs: "alice@ex.com, bob@ex.com" or "Alice <alice@ex.com>"

    Returns:
        First email address or empty string
    """
    if not to_addrs:
        return ""

    # Split by comma and get first
    first = to_addrs.split(",")[0].strip()

    # Extract email from "Name <email>" format
    if "<" in first and ">" in first:
        start = first.index("<") + 1
        end = first.index(">")
        return first[start:end].strip()

    return first


def format_sender_display(name, email):
    """
    Format sender display string from name and email.

    Args:
        name: Sender name
        email: Email address

    Returns:
        str: Formatted display string
    """
    email = (email or "").strip().lower()
    name = (name or "").strip()
    if name and email:
        if email.lower() in name.lower():
            return name
        return f"{name} <{email}>"
    return email or name or ""
