# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Access Control Service: Validates user access to mailbox accounts.
"""

from odoo import SUPERUSER_ID
from odoo.exceptions import UserError


class AccessControl:
    """Validates access to mailbox resources."""

    def __init__(self, env):
        self._env = env

    def check_account_access(self, account):
        """
        Check if current user has access to the account.

        Args:
            account: mailbox.account record

        Raises:
            UserError: If access denied
        """
        if self._env.uid == SUPERUSER_ID:
            return

        if not account:
            raise UserError(self._env._("Mailbox account is required."))

        if (
            not self._env.user.has_group("maildesk_mail_client.group_mailbox_admin")
            and self._env.user not in account.access_user_ids
        ):
            raise UserError(
                self._env._("You do not have access to this mailbox account.")
            )
