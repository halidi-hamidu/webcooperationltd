# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Trust Partner Adapter.

Implements infrastructure integration for Trust Partner Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from email.utils import parseaddr


class TrustPartnerAdapter:
    def __init__(self, env):
        self.env = env

    def partner_search(self, domain):
        return self.env["res.partner"].search(domain, limit=1)

    def partner_browse(self, partner_id):
        return self.env["res.partner"].browse(partner_id)

    def partner_exists(self, partner):
        return partner.exists()

    def partner_create(self, vals):
        return self.env["res.partner"].create(vals)

    def partner_write(self, partner, vals):
        partner.write(vals)

    def partner_id(self, partner):
        return partner.id

    def partner_trusted_by_user_id(self, partner):
        return partner.trusted_by_user_id

    def env_user_id(self):
        return self.env.user.id

    def env_translate(self, text):
        return self.env._(text)

    def extract_email_address(self, email_from):
        return parseaddr(email_from)[1] if email_from else ""
