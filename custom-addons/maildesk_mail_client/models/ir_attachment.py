# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

from odoo import api, fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    content_id = fields.Char(
        string="Content-ID",
        help="MIME Content-ID for inline attachments (e.g. <cid>)",
        index=True,
    )

    @api.model
    def _storage(self):
        """Return 'db' when force_db_storage context is set to skip filestore."""
        if self.env.context.get("force_db_storage"):
            return "db"
        return super()._storage()
