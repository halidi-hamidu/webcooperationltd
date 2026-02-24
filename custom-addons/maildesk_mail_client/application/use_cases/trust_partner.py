# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Trust Partner.

Implements the application-level use case for Trust Partner.
Layer: application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol


class TrustPartnerDeps(Protocol):
    """Dependencies for trusting a partner."""

    def partner_search(self, domain: list) -> Any: ...
    def partner_browse(self, partner_id: int) -> Any: ...
    def partner_exists(self, partner: Any) -> bool: ...
    def partner_create(self, vals: dict) -> Any: ...
    def partner_write(self, partner: Any, vals: dict) -> None: ...
    def partner_id(self, partner: Any) -> int: ...
    def partner_trusted_by_user_id(self, partner: Any) -> Any: ...
    def env_user_id(self) -> int: ...
    def env_translate(self, text: str) -> str: ...
    def extract_email_address(self, email_from: str) -> str: ...


@dataclass(frozen=True)
class TrustPartnerParams:
    """Parameters for marking a partner as trusted."""

    message: Dict[
        str, Any
    ]  # Message dict with email_from, sender_display_name, avatar_partner_id


class TrustPartner:
    """
    Mark a partner as trusted based on message sender information.

    Creates partner if needed, then sets trusted_partner=True and trusted_by_user_id.
    """

    def __init__(self, deps: TrustPartnerDeps):
        self._deps = deps

    def execute(self, params: TrustPartnerParams) -> Dict[str, Any]:
        """
        Trust a partner from message data.

        Returns:
            dict: {partner_id, trusted_partner, trusted_by_user_id, avatar_partner_id}

        Raises:
            UserError: If message data is invalid or email cannot be determined
        """
        message = params.message
        if not isinstance(message, dict):
            raise Exception(self._deps.env_translate("Invalid message data"))

        email_from = (message.get("email_from") or "").strip()
        sender_name = (message.get("sender_display_name") or email_from).strip()

        email = self._deps.extract_email_address(email_from)
        if not email:
            raise Exception(
                self._deps.env_translate("Unable to determine e-mail address")
            )

        # Try to find existing partner
        partner = False
        avatar_partner_id = message.get("avatar_partner_id")
        if avatar_partner_id:
            partner = self._deps.partner_browse(avatar_partner_id)
            if not self._deps.partner_exists(partner):
                partner = False

        if not partner:
            partner = self._deps.partner_search([("email", "=ilike", email)])

        if not partner:
            partner = self._deps.partner_create(
                {
                    "name": sender_name or email,
                    "email": email,
                }
            )

        # Mark as trusted
        self._deps.partner_write(
            partner,
            {
                "trusted_partner": True,
                "trusted_by_user_id": self._deps.env_user_id(),
            },
        )

        trusted_by = self._deps.partner_trusted_by_user_id(partner)
        return {
            "partner_id": self._deps.partner_id(partner),
            "trusted_partner": True,
            "trusted_by_user_id": trusted_by.id if trusted_by else False,
            "avatar_partner_id": self._deps.partner_id(partner),
        }
