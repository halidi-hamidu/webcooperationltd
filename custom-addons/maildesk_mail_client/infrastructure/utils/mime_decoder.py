# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
MIME Header Decoder Utility (Infrastructure Layer)

Clean Architecture:
- Pure utility function
- No business logic
- No external dependencies beyond Python stdlib
- Single Responsibility: decode MIME-encoded headers (RFC 2047)
"""

from email.header import decode_header


def decode_mime_header(value):
    """
    Decode MIME-encoded email header (RFC 2047).

    Handles formats like:
    - =?utf-8?B?SGVsbG8gV29ybGQ=?=  (Base64)
    - =?utf-8?Q?Hello_World?=        (Quoted-printable)
    - Mixed encoded and plain text

    Args:
        value: Header value (str or bytes)

    Returns:
        str: Decoded header text

    Examples:
        >>> decode_mime_header("=?utf-8?B?SGVsbG8=?=")
        'Hello'

        >>> decode_mime_header("Plain text")
        'Plain text'

        >>> decode_mime_header(b"=?utf-8?B?SGVsbG8=?=")
        'Hello'
    """
    if not value:
        return ""

    # Convert bytes to string if needed
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # If already a string and not MIME-encoded, return as-is
    if not isinstance(value, str):
        return str(value) if value else ""

    try:
        # decode_header returns list of (decoded_bytes, charset) tuples
        decoded_parts = decode_header(value)

        # Reconstruct the string
        result_parts = []
        for part_bytes, charset in decoded_parts:
            if isinstance(part_bytes, bytes):
                # Decode bytes using specified charset or fallback to utf-8
                if charset:
                    try:
                        result_parts.append(part_bytes.decode(charset, errors="ignore"))
                    except (LookupError, UnicodeDecodeError):
                        # Unknown charset or decode error - fallback to utf-8
                        result_parts.append(part_bytes.decode("utf-8", errors="ignore"))
                else:
                    # No charset specified - assume utf-8
                    result_parts.append(part_bytes.decode("utf-8", errors="ignore"))
            else:
                # Already a string
                result_parts.append(str(part_bytes))

        return "".join(result_parts)

    except Exception:
        # Fallback: return original value if decoding fails
        return value


def decode_address_display_name(name, fallback=""):
    """
    Decode email address display name (may be MIME-encoded).

    Args:
        name: Display name (str or bytes)
        fallback: Fallback value if decoding fails

    Returns:
        str: Decoded display name
    """
    if not name:
        return fallback

    decoded = decode_mime_header(name)
    return decoded if decoded else fallback
