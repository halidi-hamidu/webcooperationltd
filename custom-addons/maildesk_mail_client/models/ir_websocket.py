# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Ir WebSocket.

Defines Odoo ORM models and server-side APIs for Ir WebSocket.
Layer: odoo models.
"""

import re

import logging


from odoo import models
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _build_bus_channel_list(self, channels):
        """
        Securely map MailDesk frontend channel strings to recordset channels.

        Rationale (Odoo bus design):
        - The websocket "subscribe" event only accepts *string* channels from JS.
        - String channels are not access-checked by default and must therefore
          not be guessable when used directly (see bus.bus._sendone docstring).
        - Odoo Mail solves this by mapping guessable strings (e.g.
          "discuss.channel_42") to recordset channels with ACL/record rules.

        MailDesk uses mailbox account access boundaries. The frontend can request
        subscription to:
            "mailbox.account_<id>"
        This method converts those to the corresponding `mailbox.account`
        recordsets, but only for accounts the current user is allowed to access
        (via `access_user_ids`).
        """
        channels = list(channels)  # do not alter original list

        account_ids = []
        subscribe_user_channel = False
        for channel in list(channels):
            if not isinstance(channel, str):
                continue
            if channel == "maildesk.user":
                channels.remove(channel)
                subscribe_user_channel = True
                continue
            match = re.findall(r"mailbox\.account_(\d+)", channel)
            if not match:
                continue
            channels.remove(channel)
            account_ids.append(int(match[0]))

        if subscribe_user_channel:
            _logger.info(
                "[MailDesk Bus] websocket subscribe mapping: uid=%s requested_user_channel=True",
                self.env.uid,
            )
            channels.append(self.env["res.users"].browse(self.env.uid))

        if account_ids:
            user = self.env.user
            is_admin = self.env.uid == SUPERUSER_ID or user.has_group(
                "maildesk_mail_client.group_mailbox_admin"
            )
            if is_admin:
                accounts = self.env["mailbox.account"].browse(account_ids).exists()
            elif user.has_group("maildesk_mail_client.group_mailbox_user"):
                accounts = self.env["mailbox.account"].search(
                    [
                        ("id", "in", account_ids),
                        ("access_user_ids", "in", [self.env.uid]),
                    ]
                )
            else:
                return super()._build_bus_channel_list(channels)

            _logger.info(
                "[MailDesk Bus] websocket subscribe mapping: uid=%s requested=%s resolved=%s",
                self.env.uid,
                sorted(set(account_ids)),
                sorted(accounts.ids),
            )
            channels.extend(accounts)

        return super()._build_bus_channel_list(channels)
