# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Mailbox Account Wizard.

Defines transient wizard models and actions for Mailbox Account Wizard.
Layer: odoo wizards.
"""

from odoo import fields, models
from odoo.exceptions import UserError


class MailboxAccountWizard(models.TransientModel):
    _name = "mailbox.account.wizard"
    _description = "Connect to Existing Mailbox Wizard"

    email = fields.Char(
        "Email Address",
        required=True,
        help="Enter the email address of the shared mailbox you want to connect to.",
    )
    password = fields.Char(
        required=True,
        help="Enter the shared password provided by the mailbox owner.",
    )

    def action_connect_mailbox(self):
        """
        Grants the current user access to a shared mailbox after verifying the
        provided email and password. Searches for an active shared account,
        blocks duplicate access grants, validates credentials, and adds the user
        to the allowed list before triggering a UI reload.
        """
        account = (
            self.env["mailbox.account"]
            .sudo()
            .search(
                [
                    ("email", "=", self.email.strip()),
                    ("is_shared", "=", True),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )
        if not account:
            raise UserError(self.env._("No shared mailbox found with this email."))
        if self.env.user in account.access_user_ids:
            raise UserError(self.env._("You already have access to this mailbox."))

        if account.password != self.password:
            raise UserError(self.env._("Incorrect password."))

        account.sudo().write(
            {
                "access_user_ids": [(4, self.env.user.id)],
            }
        )

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
