# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Mail Message Tag.

Defines Odoo ORM models and server-side APIs for Mail Message Tag.
Layer: odoo models.
"""

from odoo import api, fields, models


class MailMessageTag(models.Model):
    _name = "mail.message.tag"
    _description = "Message Tag"

    name = fields.Char(required=True, translate=True)
    color = fields.Char(default="#6CC1ED")

    @api.model
    def get_tag_list(self):
        """
        Return all available tags for the current user.
        Used by frontend to populate tag selectors and filters.

        Returns:
            list: List of tag dicts with id, name, color
        """
        tags = self.search([])
        return [{"id": t.id, "name": t.name, "color": t.color} for t in tags]
