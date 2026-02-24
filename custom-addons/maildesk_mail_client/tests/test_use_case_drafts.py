# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for draft-related use cases.

Covers:
- `application/use_cases/save_draft.py`
- `application/use_cases/load_draft.py`
- `application/use_cases/delete_draft.py`
Layer: tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from odoo.tests.common import TransactionCase

from ..application.use_cases.delete_draft import DeleteDraft, DeleteDraftParams
from ..application.use_cases.load_draft import LoadDraft, LoadDraftParams
from ..application.use_cases.save_draft import SaveDraft, SaveDraftParams


@dataclass
class _DummyAccount:
    id: int
    sender_name: str = "Sender"
    name: str = "Account"
    email: str = "acc@example.com"


@dataclass
class _DummyAttachment:
    id: int
    name: str
    mimetype: str


@dataclass
class _DummyDraft:
    id: int
    account_id: _DummyAccount
    subject: str = ""
    body_html: str = ""
    to_emails: str = ""
    cc_emails: str = ""
    bcc_emails: str = ""
    attachment_ids: list = field(default_factory=list)
    reply_to_cache_uid: str = ""
    request_read_receipt: bool = False
    request_delivery_receipt: bool = False
    sender_display_name: str = ""
    model: str = ""
    res_id: int = 0
    reply_to_message_id: str = ""
    tag_ids: list = field(default_factory=list)


class _TextHelper:
    def to_text(self, items):
        return ", ".join(items or [])

    def to_list(self, text):
        if not text:
            return []
        return [x.strip() for x in (text or "").split(",") if x.strip()]


class _DraftRepo:
    def __init__(self, draft: _DummyDraft | None = None):
        self._draft = draft
        self.updated_vals = None
        self.created_vals = None
        self.deleted = False

    def browse(self, draft_id):
        return self._draft if self._draft and self._draft.id == int(draft_id) else None

    def exists(self, draft):
        return bool(draft)

    def update(self, draft, vals):
        self.updated_vals = vals

    def create(self, vals):  # pylint: disable=method-required-super
        self.created_vals = vals
        return _DummyDraft(id=999, account_id=_DummyAccount(id=int(vals["account_id"])))

    def delete(self, _draft):
        self.deleted = True


class TestDraftUseCases(TransactionCase):
    """Unit tests for draft use cases (no DB required)."""

    def test_save_draft_updates_existing_and_preserves_id(self):
        """Updating an existing draft calls repo.update and returns the existing id."""

        repo = _DraftRepo(draft=_DummyDraft(id=10, account_id=_DummyAccount(id=1)))
        use_case = SaveDraft(repo, _TextHelper(), self.env)

        draft_id = use_case.execute(
            SaveDraftParams(
                account_id=1,
                draft_id=10,
                subject="S",
                body_html="<p>B</p>",
                to=["a@example.com"],
                attachment_ids=[1, 2],
            )
        )

        self.assertEqual(draft_id, 10)
        self.assertIsNotNone(repo.updated_vals)
        self.assertEqual(repo.updated_vals["to_emails"], "a@example.com")
        self.assertEqual(repo.updated_vals["attachment_ids"], [(6, 0, [1, 2])])

    def test_save_draft_creates_new_when_missing(self):
        """When the referenced draft doesn't exist, SaveDraft creates a new record."""

        repo = _DraftRepo(draft=None)
        helper = _TextHelper()
        env = self.env  # Add env for normalization service

        use_case = SaveDraft(repo, helper, env)

        draft_id = use_case.execute(
            SaveDraftParams(
                account_id=1,
                draft_id=10,
                subject="S",
                to=[],
                attachment_ids=[],
            )
        )

        self.assertEqual(draft_id, 999)
        self.assertIsNotNone(repo.created_vals)
        self.assertEqual(repo.created_vals["attachment_ids"], [(5, 0, 0)])

    def test_load_draft_returns_structured_dto(self):
        """LoadDraft returns a UI-friendly dict (lists for recipients, attachment metadata)."""

        draft = _DummyDraft(
            id=10,
            account_id=_DummyAccount(id=1, sender_name="Acc Sender"),
            subject="Hello",
            body_html="<p>Body</p>",
            to_emails="a@example.com, b@example.com",
            attachment_ids=[
                _DummyAttachment(id=1, name="a.txt", mimetype="text/plain")
            ],
        )
        repo = _DraftRepo(draft=draft)
        use_case = LoadDraft(repo, _TextHelper())

        dto = use_case.execute(LoadDraftParams(draft_id=10))

        self.assertEqual(dto["id"], 10)
        self.assertEqual(dto["account_id"], 1)
        self.assertEqual(dto["to"], ["a@example.com", "b@example.com"])
        self.assertEqual(dto["attachments"][0]["id"], 1)

    def test_delete_draft_deletes_when_found(self):
        """DeleteDraft deletes and returns True when draft exists."""

        repo = _DraftRepo(draft=_DummyDraft(id=10, account_id=_DummyAccount(id=1)))
        use_case = DeleteDraft(repo)

        res = use_case.execute(DeleteDraftParams(draft_id=10))

        self.assertTrue(res)
        self.assertTrue(repo.deleted)
