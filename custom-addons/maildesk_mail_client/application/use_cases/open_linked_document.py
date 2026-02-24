# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Open Linked Document.

Implements the application-level use case for Open Linked Document.
Layer: application.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class OpenLinkedDocumentDeps(Protocol):
    """Dependencies for opening linked documents."""

    def env_browse(self, model: str, res_id: int) -> Any: ...
    def env_exists(self, record: Any) -> bool: ...
    def env_search_view(self, model: str) -> Any: ...
    def env_translate(self, text: str, **kwargs) -> str: ...
    def record_display_name(self, record: Any) -> str: ...
    def view_id(self, view: Any) -> int: ...


@dataclass(frozen=True)
class OpenLinkedDocumentParams:
    """Parameters for opening a linked document."""

    model: str
    res_id: int


class OpenLinkedDocument:
    """
    Open a linked Odoo document in a form view.

    Returns an ir.actions.act_window action dict to open the record.
    """

    def __init__(self, deps: OpenLinkedDocumentDeps):
        self._deps = deps

    def execute(self, params: OpenLinkedDocumentParams) -> Any:
        """
        Generate action to open document.

        Returns:
            dict: ir.actions.act_window action or False if record doesn't exist
        """
        if not params.model or not params.res_id:
            return False

        record = self._deps.env_browse(params.model, int(params.res_id))
        if not self._deps.env_exists(record):
            return False

        view = self._deps.env_search_view(params.model)
        name = (
            self._deps.record_display_name(record) or f"{params.model} #{params.res_id}"
        )

        return {
            "type": "ir.actions.act_window",
            "name": self._deps.env_translate("Open: %(name)s", name=name),
            "res_model": params.model,
            "res_id": int(params.res_id),
            "view_mode": "form",
            "views": [[self._deps.view_id(view), "form"]]
            if view
            else [[False, "form"]],
            "target": "current",
        }
