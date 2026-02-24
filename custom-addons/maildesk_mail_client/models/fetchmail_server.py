# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Fetchmail Server.

Defines Odoo ORM models and server-side APIs for Fetchmail Server.
Layer: odoo models.
"""

import logging

from odoo import api, models, tools

_logger = logging.getLogger(__name__)


class FetchmailServer(models.Model):
    _inherit = "fetchmail.server"

    def _is_maildesk_outlook_graph_server(self):
        """
        Return True if this fetchmail.server is used by a MailDesk Outlook Graph
        mailbox account (Graph token stored on mailbox.account), in which case
        Odoo's IMAP login test must be bypassed.
        """
        self.ensure_one()
        if self.server_type != "outlook":
            return False

        Account = self.env["mailbox.account"].sudo()
        return bool(
            Account.search(
                [
                    ("mail_server_id", "=", self.id),
                    ("outlook_graph_access_token", "!=", False),
                ],
                limit=1,
            )
        )

    def button_confirm_login(self):
        """
        Odoo's standard "Confirm Login" always tries to connect+authenticate via
        IMAP (connect()->_imap_login). This is incorrect for MailDesk Outlook
        Graph accounts: Graph tokens are not valid for IMAP (different audience
        and permissions).

        For MailDesk Graph accounts, short-circuit the check and mark the server
        as confirmed without touching IMAP. For all other servers, keep Odoo's
        behavior unchanged.
        """
        graph_servers = self.filtered(lambda s: s._is_maildesk_outlook_graph_server())
        if graph_servers:
            graph_servers.write({"state": "done"})

        other_servers = self - graph_servers
        if other_servers:
            return super(FetchmailServer, other_servers).button_confirm_login()
        return True

    def _maildesk_used_server_ids(self):
        """
        Return IDs of fetchmail servers linked to active MailDesk accounts so
        they can be excluded from regular Odoo fetchmail processing. Uses sudo
        to bypass access restrictions when inspecting mailbox accounts.
        """
        Account = self.env["mailbox.account"].sudo()
        return Account.search([], limit=50000).mapped("mail_server_id").ids

    @api.model
    def _fetch_mails(self, **kw):
        """
        Cron hook that fetches mail only for servers not controlled by MailDesk,
        preserving Odoo's standard behavior for unrelated accounts. It builds a
        domain of active non-local servers and delegates fetching to the filtered
        set.
        """
        base_domain = [("state", "=", "done"), ("server_type", "!=", "local")]
        used_ids = set(self._maildesk_used_server_ids())
        to_fetch = self.search(base_domain).filtered(lambda s: s.id not in used_ids)
        to_fetch._fetch_mail(**kw)

        # MailDesk Polling Hook
        # Never run provider sync side effects during Odoo test runs.
        if tools.config.get("test_enable") or tools.config.get("test_file"):
            return
        try:
            self.env["maildesk.polling_orchestrator"].run_cron()
        except Exception:
            # Prevent MailDesk errors from blocking standard Odoo fetchmail
            _logger.exception("MailDesk polling orchestrator failed")

    def fetch_mail(self):
        """
        Entry point for manual or cron fetching that bypasses MailDesk-managed
        servers while letting others use the standard fetchmail logic. If no
        MailDesk servers exist, it falls back to the parent implementation.
        """
        used_ids = set(self._maildesk_used_server_ids())
        if not used_ids:
            return super().fetch_mail()

        servers_to_fetch = self.filtered(lambda s: s.id not in used_ids)

        # Early return if all servers in this recordset are MailDesk-managed
        if not servers_to_fetch:
            return

        for server in servers_to_fetch:
            super(FetchmailServer, server).fetch_mail()
