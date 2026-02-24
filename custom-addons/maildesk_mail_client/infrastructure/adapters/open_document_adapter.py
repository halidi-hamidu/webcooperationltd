# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
OpenDocument Adapter: Implements deps protocol for OpenLinkedDocument use-case.
"""


class OpenDocumentAdapter:
    def __init__(self, env):
        self.env = env

    def env_browse(self, model, res_id):
        return self.env[model].browse(res_id)

    def env_exists(self, record):
        return record.exists()

    def env_search_view(self, model):
        return self.env["ir.ui.view"].search(
            [("model", "=", model), ("type", "=", "form")],
            order="priority",
            limit=1,
        )

    def env_translate(self, text, **kwargs):
        return self.env._(text, **kwargs)

    def record_display_name(self, record):
        return record.display_name

    def view_id(self, view):
        return view.id if view else False
