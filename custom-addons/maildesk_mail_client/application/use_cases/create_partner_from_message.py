# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Create Partner From Message.

Implements the application-level use case for Create Partner From Message.
Layer: application.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


class CreatePartnerFromMessageDeps(Protocol):
    """Dependencies for creating a partner from message data."""

    def partner_search(self, domain: list) -> Any: ...
    def partner_create(self, vals: dict) -> Any: ...
    def partner_id(self, partner: Any) -> int: ...
    def env_translate(self, text: str) -> str: ...
    def defaults_from_email(self, email: str, display_name: str) -> dict: ...
    def get_valid_lang(self, lang: str) -> str: ...


@dataclass(frozen=True)
class CreatePartnerFromMessageParams:
    """Parameters for creating a partner from message."""

    message_id: Optional[str] = None  # Not currently used
    email_from: Optional[str] = None
    sender_display_name: Optional[str] = None


class CreatePartnerFromMessage:
    """
    Create or open a partner from message sender information.

    Returns an ir.actions.act_window to open the partner form in a dialog.
    If partner already exists, opens existing partner instead of creating new.
    """

    def __init__(self, deps: CreatePartnerFromMessageDeps):
        self._deps = deps

    def execute(self, params: CreatePartnerFromMessageParams) -> Dict[str, Any]:
        """
        Create/open partner from email.

        Returns:
            dict: ir.actions.act_window action to open partner form

        Raises:
            UserError: If email address is missing
        """
        email = (params.email_from or "").strip()
        display_name = (params.sender_display_name or "").strip()

        # Extract email using regex
        m = re.search(r"<?([A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+[.][A-Za-z0-9-]+)>?", email)
        email = (m.group(1) if m else email).lower()

        if not email:
            raise Exception(self._deps.env_translate("Email address is missing."))

        # Get defaults from email domain
        defaults = self._deps.defaults_from_email(email, display_name)

        # Search for existing partner
        partner = self._deps.partner_search([("email", "=ilike", email)])

        if not partner:
            partner = self._deps.partner_create(
                {
                    "name": defaults["name"],
                    "email": email,
                    "lang": self._deps.get_valid_lang(defaults["lang"]),
                    "tz": defaults["tz"],
                    "website": defaults["website"],
                }
            )

        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "res_id": self._deps.partner_id(partner),
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "create_partner_return_to_maildesk": True,
            },
        }
