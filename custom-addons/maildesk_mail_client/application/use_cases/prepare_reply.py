# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
PrepareReply Use-Case: Prepares reply/reply-all composer data.
Returns structured dict for UI consumption.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

from .sanitize_message_body import SanitizeMessageBody, SanitizeMessageBodyParams
from ...infrastructure.adapters.sanitize_adapter import SanitizeAdapter


@dataclass(frozen=True)
class PrepareReplyParams:
    """Parameters for preparing reply composer."""

    msg_key: Any  # Can be index_id (int) or triplet "account|folder|uid"
    reply_all: bool = False


class PrepareReplyDeps(Protocol):
    """Dependencies required by PrepareReply use case."""

    def get_message(self, msg_key: Any) -> Dict[str, Any]:
        """Fetch full message data for composer."""
        ...

    def get_account_email(self, account_id: int) -> str:
        """Get account email for filtering."""
        ...

    def get_account_sender_name(self, account_id: int) -> str:
        """Get account sender name."""
        ...

    def parse_email_list(self, email_str: str) -> List[str]:
        """Parse comma-separated email list."""
        ...


class PrepareReply:
    """
    Use-case: Prepare reply or reply-all composer data.

    Responsibilities:
    - Fetch original message
    - Determine recipients (reply vs reply-all)
    - Format quoted body
    - Build composer DTO
    """

    def __init__(self, deps: PrepareReplyDeps):
        self._deps = deps

    def execute(self, params: PrepareReplyParams) -> Dict[str, Any]:
        """
        Execute reply preparation.

        Args:
            params: PrepareReplyParams

        Returns:
            Dict with: to, cc, subject, body_html, account_id, attachments, from_display
        """
        msg = self._deps.get_message(params.msg_key)
        if not msg:
            return {}

        # Extract account_id
        account_id = self._extract_account_id(msg)
        own_email = self._deps.get_account_email(account_id)
        from_display = self._deps.get_account_sender_name(account_id)

        # Prepare recipients
        to, cc = self._build_recipients(msg, params.reply_all, own_email)

        # Prepare subject
        subject = self._build_subject(msg)

        # Prepare quoted body
        body_html = self._build_quoted_body(msg)

        return {
            "to": to,
            "cc": cc,
            "subject": subject,
            "body_html": body_html,
            "account_id": account_id,
            "attachments": [],  # No attachments in reply
            "from_display": from_display,
        }

    def _extract_account_id(self, msg: Dict[str, Any]) -> int:
        """Extract account_id from message (handle both int and [id, name] format)."""
        account_id = msg.get("account_id")
        if isinstance(account_id, list):
            return account_id[0]
        return account_id

    def _build_recipients(
        self, msg: Dict[str, Any], reply_all: bool, own_email: str
    ) -> tuple:
        """Build TO and CC lists based on reply mode."""
        to = []
        cc = []

        sender = msg.get("email_from") or msg.get("from_addr", "")

        if reply_all:
            # TO: original FROM + all TO except own
            if sender:
                to.append(sender)

            to_addrs = msg.get("to_addrs") or msg.get("to_display", "")
            if to_addrs:
                for addr in self._deps.parse_email_list(to_addrs):
                    if addr.lower() != own_email.lower() and addr not in to:
                        to.append(addr)

            # CC: all original CC except own
            cc_addrs = msg.get("cc_addrs") or msg.get("cc_display", "")
            if cc_addrs:
                for addr in self._deps.parse_email_list(cc_addrs):
                    if addr.lower() != own_email.lower():
                        cc.append(addr)
        else:
            # Simple reply: TO = original FROM
            if sender:
                to.append(sender)

        return to, cc

    def _build_subject(self, msg: Dict[str, Any]) -> str:
        """Build reply subject with Re: prefix."""
        original_subject = msg.get("subject", "")
        if not original_subject.startswith("Re:"):
            return f"Re: {original_subject}"
        return original_subject

    def _build_quoted_body(self, msg: Dict[str, Any]) -> str:
        """Build quoted reply body with attribution."""
        original_body = msg.get("body_original") or msg.get("body_html", "")

        # Optionally sanitize original body (remove tracking)
        # If account has blocking enabled, this will be applied
        try:
            account_id = self._extract_account_id(msg)
            sanitize_adapter = SanitizeAdapter(None)  # Will be injected properly
            # For now, check setting directly in adapter
            if hasattr(self._deps, "env"):
                sanitize_adapter.env = self._deps.env
                sanitize_params = SanitizeMessageBodyParams(
                    body_html=original_body, account_id=account_id
                )
                sanitize_use_case = SanitizeMessageBody(sanitize_adapter)
                original_body = sanitize_use_case.execute(sanitize_params)
        except Exception:
            # If sanitization fails, use original
            pass

        sender_name = msg.get("sender_display_name") or msg.get("email_from", "")
        date_str = msg.get("formatted_date") or msg.get("date", "")

        attribution = f"<p>On {date_str}, {sender_name} wrote:</p>"
        quoted = f'<blockquote style="margin: 0 0 0 0.8ex; border-left: 1px solid #ccc; padding-left: 1ex;">{original_body}</blockquote>'

        # Wrap in div with class for signature insertion marker
        return f'<div class="o-maildesk-quoted-content">{attribution}{quoted}</div>'
