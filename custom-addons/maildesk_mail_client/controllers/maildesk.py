# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk MailDesk.

Defines HTTP/JSON endpoints used by the MailDesk UI for MailDesk.
Layer: odoo controllers.
"""

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class MailDeskController(http.Controller):
    @http.route("/maildesk", type="http", auth="user", website=True)
    def open_maildesk(self, **kwargs):
        """
        Redirect authorized mailbox users to the MailDesk action while sending
        unauthorized users back to the Odoo web home to avoid exposing the
        feature to non-members.
        """
        if not request.env.user.has_group("maildesk_mail_client.group_mailbox_user"):
            return request.redirect("/web")
        return request.redirect("/web#action=maildesk_mail_client.maildesk_action")
