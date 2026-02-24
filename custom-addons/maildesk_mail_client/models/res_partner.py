# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Res Partner.

Defines Odoo ORM models and server-side APIs for Res Partner.
Layer: odoo models.
"""

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    trusted_partner = fields.Boolean(default=False)
    trusted_by_user_id = fields.Many2one("res.users")

    maildesk_email_count = fields.Integer(
        string="Email Count",
        compute="_compute_maildesk_email_count",
    )

    def _maildesk_email_match(self) -> str | None:
        """Return the email filter string used by MailDesk for this partner.

        - For contacts: the exact email address (lowercased).
        - For companies: the email domain (e.g. '@acme.example') so that any
          address within the domain matches.
        """
        self.ensure_one()
        email = (self.email or "").strip().lower()
        if not email:
            return None
        if self.is_company and "@" in email:
            domain_part = email.split("@", 1)[1].strip()
            if domain_part:
                return f"@{domain_part}"
        return email

    def _compute_maildesk_email_count(self):
        """Compute the number of related MailDesk emails visible to the user."""
        allowed_account_ids = (
            self.env["mailbox.account"]
            .sudo()
            .search([("access_user_ids", "in", self.env.user.id)])
            .ids
        )
        if not allowed_account_ids:
            for p in self:
                p.maildesk_email_count = 0
            return

        Index = self.env["maildesk.message_index"].sudo()
        for p in self:
            match = p._maildesk_email_match()
            if not match:
                p.maildesk_email_count = 0
                continue

            count = Index.search_count(
                [
                    ("account_id", "in", allowed_account_ids),
                    "|",
                    "|",
                    "|",
                    ("from_addr", "ilike", match),
                    ("to_addrs", "ilike", match),
                    ("cc_addrs", "ilike", match),
                    ("bcc_addrs", "ilike", match),
                    ("deleted_on_server", "!=", True),
                    ("pending_delete", "!=", True),
                ]
            )
            p.maildesk_email_count = count

    def trust_sender(self):
        """
        Mark this partner as a trusted sender.
        Used by the frontend trust action (maildesk trust button).
        """
        for partner in self:
            partner.write(
                {
                    "trusted_partner": True,
                    "trusted_by_user_id": self.env.user.id,
                }
            )
        return True

    @api.model
    def count_partners_with_email_activity(self, domain=None):
        """
        Count partners that have an email address, optionally filtered by an
        additional domain. Enables dashboards to quickly gauge how many contacts
        participate in email communication without fetching full records.
        """
        return self.search_count([("email", "!=", False)] + (domain or []))

    @api.model
    def get_partners_with_email_activity(self, domain=None, offset=0, limit=20):
        """
        Fetch partners possessing email addresses with optional domain, offset,
        and limit, then return only lightweight identity fields. This supports
        autocomplete and lookup features without loading heavy relational data.
        """
        partners = self.search(
            [("email", "!=", False)] + (domain or []),
            offset=offset,
            limit=limit,
        )
        return partners.read(["id", "name", "email", "company_name", "category_id"])

    def email_history(self):
        """Open MailDesk prefiltered to this partner.

        For companies, the filter matches the whole email domain rather than a
        single mailbox.
        """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "maildesk_mail_client.maildesk_action",
            "name": self.env._("Sent Emails"),
            "params": {
                "email_from": (self._maildesk_email_match() or "").lower(),
                "partner_id": self.id,
                "partner_name": self.name,
            },
        }
