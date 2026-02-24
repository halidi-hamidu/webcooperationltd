# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Create Partner Adapter.

Implements infrastructure integration for Create Partner Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from ...models.utils_email_defaults import defaults_from_email
from ..utils.lang_validator import get_valid_lang


class CreatePartnerAdapter:
    def __init__(self, env):
        self.env = env

    def partner_search(self, domain):
        return self.env["res.partner"].search(domain, limit=1)

    def partner_create(self, vals):
        return self.env["res.partner"].create(vals)

    def partner_id(self, partner):
        return partner.id

    def env_translate(self, text):
        return self.env._(text)

    def defaults_from_email(self, email, display_name):
        return defaults_from_email(email, display_name)

    def get_valid_lang(self, lang):
        return self._get_valid_lang(lang)

    def _get_valid_lang(self, lang):
        return get_valid_lang(lang, self.env)
