# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `application/use_cases/open_linked_document.py`.

Focus: action dict shape and existence checks.
Layer: tests.
"""

from __future__ import annotations

from odoo.tests.common import TransactionCase

from ..application.use_cases.open_linked_document import (
    OpenLinkedDocument,
    OpenLinkedDocumentParams,
)


class TestOpenLinkedDocument(TransactionCase):
    """Unit tests for opening linked documents."""

    def test_returns_false_when_record_missing(self):
        """Missing record yields False (no action)."""

        class Deps:
            def env_browse(self, _model: str, _res_id: int):
                return object()

            def env_exists(self, _record) -> bool:
                return False

            def env_search_view(self, _model: str):
                return None

            def env_translate(self, text: str, **kwargs) -> str:
                return text % kwargs if kwargs else text

            def record_display_name(self, _record):
                return ""

            def view_id(self, _view) -> int:
                return 0

        res = OpenLinkedDocument(Deps()).execute(
            OpenLinkedDocumentParams(model="res.partner", res_id=1)
        )
        self.assertFalse(res)

    def test_builds_act_window_action_for_existing_record(self):
        """Existing record returns an act_window action in form mode."""

        class DummyView:
            id = 99

        class DummyRecord:
            display_name = "Partner A"

        class Deps:
            def env_browse(self, _model: str, _res_id: int):
                return DummyRecord()

            def env_exists(self, record) -> bool:
                return isinstance(record, DummyRecord)

            def env_search_view(self, _model: str):
                return DummyView()

            def env_translate(self, text: str, **kwargs) -> str:
                return text.replace("%(name)s", kwargs.get("name"))

            def record_display_name(self, record):
                return record.display_name

            def view_id(self, view) -> int:
                return view.id

        action = OpenLinkedDocument(Deps()).execute(
            OpenLinkedDocumentParams(model="res.partner", res_id=1)
        )
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["res_id"], 1)
        self.assertEqual(action["views"], [[99, "form"]])
