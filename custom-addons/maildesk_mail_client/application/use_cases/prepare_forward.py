# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
PrepareForward Use-Case: Prepares forward composer data.
Returns structured dict with attachments for UI consumption.
"""

from dataclasses import dataclass
from typing import Any, Dict, Protocol

from .sanitize_message_body import SanitizeMessageBody, SanitizeMessageBodyParams
from ...infrastructure.adapters.sanitize_adapter import SanitizeAdapter


@dataclass(frozen=True)
class PrepareForwardParams:
    """Parameters for preparing forward composer."""

    msg_key: Any  # Can be index_id (int) or triplet "account|folder|uid"


class PrepareForwardDeps(Protocol):
    """Dependencies required by PrepareForward use case."""

    def get_message(self, msg_key: Any) -> Dict[str, Any]:
        """Fetch full message data including attachments."""
        ...

    def get_account_sender_name(self, account_id: int) -> str:
        """Get account sender name."""
        ...


class PrepareForward:
    """
    Use-case: Prepare forward composer data.

    Responsibilities:
    - Fetch original message with attachments
    - Format forwarded body with headers
    - Build composer DTO with attachments
    """

    def __init__(self, deps: PrepareForwardDeps):
        self._deps = deps

    def execute(self, params: PrepareForwardParams) -> Dict[str, Any]:
        """
        Execute forward preparation.

        Args:
            params: PrepareForwardParams

        Returns:
            Dict with: to, cc, subject, body_html, account_id, attachments, from_display
        """
        msg = self._deps.get_message(params.msg_key)
        if not msg:
            return {}

        account_id = self._extract_account_id(msg)
        from_display = self._deps.get_account_sender_name(account_id)
        subject = self._build_subject(msg)
        body_html = self._build_forwarded_body(msg)

        raw_attachments = msg.get("attachments", [])
        attachments = [
            {
                "id": a["id"],
                "name": a.get("name", ""),
                "mimetype": a.get("mimetype", ""),
                "access_token": a.get("access_token", ""),
            }
            for a in raw_attachments
            if isinstance(a.get("id"), int)
        ]

        return {
            "to": [],
            "cc": [],
            "subject": subject,
            "body_html": body_html,
            "account_id": account_id,
            "attachments": attachments,
            "from_display": from_display,
        }

    def _extract_account_id(self, msg: Dict[str, Any]) -> int:
        """Extract account_id from message (handle both int and [id, name] format)."""
        account_id = msg.get("account_id")
        if isinstance(account_id, list):
            return account_id[0]
        return account_id

    def _build_subject(self, msg: Dict[str, Any]) -> str:
        """Build forward subject with Fwd: prefix."""
        original_subject = msg.get("subject", "")
        if not original_subject.startswith("Fwd:"):
            return f"Fwd: {original_subject}"
        return original_subject

    def _build_forwarded_body(self, msg: Dict[str, Any]) -> str:
        """Build forwarded message body with headers."""
        original_body = msg.get("body_original") or msg.get("body_html", "")

        # Optionally sanitize original body (remove tracking)
        try:
            account_id = self._extract_account_id(msg)
            sanitize_adapter = SanitizeAdapter(None)
            if hasattr(self._deps, "env"):
                sanitize_adapter.env = self._deps.env
                sanitize_params = SanitizeMessageBodyParams(
                    body_html=original_body, account_id=account_id
                )
                sanitize_use_case = SanitizeMessageBody(sanitize_adapter)
                original_body = sanitize_use_case.execute(sanitize_params)
        except Exception:
            pass

        sender = msg.get("email_from") or msg.get("from_addr", "")
        date_str = msg.get("formatted_date") or msg.get("date", "")
        to_str = msg.get("to_addrs") or msg.get("to_display", "")
        subject = msg.get("subject", "")

        headers = f"""<p>---------- Forwarded message ----------</p>
<p><strong>From:</strong> {sender}<br>
<strong>Date:</strong> {date_str}<br>
<strong>Subject:</strong> {subject}<br>
<strong>To:</strong> {to_str}</p>
<br>"""

        # Wrap in div with class for signature insertion marker
        return f'<div class="o-maildesk-quoted-content">{headers}{original_body}</div>'
