# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP UTF-7 Encoding Utilities

Provides robust encoding/decoding utilities for IMAP folder names to ensure
compatibility across all IMAP servers and character sets.

IMAP uses "modified UTF-7" encoding for folder names with non-ASCII characters.
The imapclient library handles this automatically, but we need to ensure clean
UTF-8 strings are passed to it.
"""

from imapclient.imap_utf7 import decode as imap_utf7_decode

import logging

_logger = logging.getLogger(__name__)


def normalize_folder_name(raw_name):
    """
    Normalize IMAP folder name to clean UTF-8 string.

    imapclient library returns folder names as Unicode strings (UTF-8),
    already decoded from IMAP modified UTF-7. This function ensures
    we have a clean, normalized UTF-8 string.

    Args:
        raw_name: Folder name from IMAP (bytes or str)

    Returns:
        str: Clean UTF-8 folder name

    Examples:
        >>> normalize_folder_name(b'INBOX')
        'INBOX'
        >>> normalize_folder_name('Campañas')
        'Campañas'
        >>> normalize_folder_name(b'Campa\xc3\xb1as')
        'Campañas'
    """
    if not raw_name:
        return ""

    if isinstance(raw_name, bytes):
        if b"&" in raw_name:
            try:
                decoded = imap_utf7_decode(raw_name)
                if decoded and ("Ã" in decoded or "Â" in decoded):
                    decoded = decoded.encode("latin-1").decode("utf-8")
                if decoded:
                    return decoded
            except Exception:
                pass

        try:
            return raw_name.decode("utf-8")
        except UnicodeDecodeError:
            pass

        try:
            return raw_name.decode("latin-1")
        except UnicodeDecodeError:
            return raw_name.decode("utf-8", errors="replace")

    name = str(raw_name).strip()
    if "Ã" in name or "Â" in name:
        try:
            name = name.encode("latin-1").decode("utf-8")
        except Exception:
            pass
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        name = name.encode("utf-8", errors="replace").decode("utf-8")

    return name


def safe_folder_operation(operation_name, folder_name, operation_func):
    """
    Execute IMAP folder operation with robust error handling.

    Wraps folder operations (select, status, etc.) to handle encoding errors
    and provide detailed logging for debugging.

    Args:
        operation_name: Human-readable operation name (e.g., "SELECT", "STATUS")
        folder_name: Folder name to operate on
        operation_func: Callable that performs the actual IMAP operation

    Returns:
        Result from operation_func, or None if operation fails

    Example:
        >>> def get_status():
        ...     return client.folder_status(folder_name, ["UIDNEXT"])
        >>> result = safe_folder_operation("STATUS", "Campañas", get_status)
    """
    try:
        return operation_func()
    except Exception as e:
        folder_hex = _to_utf8_hex(folder_name)
        _logger.warning(
            "IMAP %s failed for folder=%s (utf8_hex=%s): %s",
            operation_name,
            _safe_repr(folder_name),
            folder_hex,
            e,
        )
        return None


def _safe_repr(value) -> str:
    """
    Produce a stable representation for logging without raising encoding errors.

    Args:
        value: Any value to represent.

    Returns:
        A string safe to include in logs.
    """
    try:
        return repr(value)
    except Exception:
        return "<unreprable>"


def _to_utf8_hex(value) -> str:
    """
    Convert a folder name into an UTF-8 byte-hex string for diagnostics.

    Args:
        value: Folder name as `str` or `bytes`.

    Returns:
        Lowercase hex string. Never raises.
    """
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray, memoryview)):
        try:
            return bytes(value).hex()
        except Exception:
            return ""
    try:
        # `backslashreplace` prevents crashes on surrogate/unencodable characters.
        return str(value).encode("utf-8", errors="backslashreplace").hex()
    except Exception:
        return ""
