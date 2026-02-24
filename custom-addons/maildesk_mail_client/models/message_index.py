# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Message Index.

Defines Odoo ORM models and server-side APIs for Message Index.
Layer: odoo models.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from odoo import api, fields, models

from ..application.use_cases.ingest_queue import (
    EnqueueIngestForMessageIndex,
    EnqueueIngestForMessageIndexParams,
)
from ..domain.services.normalization import norm_msgid
from ..infrastructure.adapters.ingest_queue_adapter import IngestQueueAdapter

_logger = logging.getLogger(__name__)


def _strip_nul_chars(value: Any) -> Any:
    """
    Remove NUL (0x00) characters from text values.

    Postgres text/varchar columns cannot contain the NUL byte. Some emails can
    legally contain NUL bytes in raw payloads, and buggy/odd MIME encodings can
    propagate them into decoded strings (e.g. subject/preview/headers). When
    those strings are inserted into `maildesk_message_index` via SQL, Postgres
    raises: "A string literal cannot contain NUL (0x00) characters."

    Args:
        value: Any supported value type. Strings/bytes are sanitized. Lists,
            tuples, and dict values are sanitized recursively.

    Returns:
        The sanitized value with all `\\x00` characters removed from textual
        content.
    """
    if value is None or value is False:
        return value
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            value = ""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, (list, tuple)):
        sanitized = [_strip_nul_chars(v) for v in value]
        return type(value)(sanitized)  # preserve list/tuple
    if isinstance(value, dict):
        return {k: _strip_nul_chars(v) for k, v in value.items()}
    return value


class MailDeskMessageIndex(models.Model):
    _name = "maildesk.message_index"
    _description = "MailDesk: Message Index (SSOT)"
    _rec_name = "subject"
    _order = "sort_ts desc, id desc"

    account_id = fields.Many2one(
        "mailbox.account",
        required=True,
        index=True,
        ondelete="cascade",
    )
    provider = fields.Selection(
        [
            ("imap", "IMAP"),
            ("gmail", "Gmail"),
            ("outlook", "Outlook"),
        ],
        required=True,
        index=True,
        default="imap",
    )
    folder = fields.Char(required=True, index=True)
    uid = fields.Char(required=True, index=True)

    message_id = fields.Char(index=True)
    outgoing_id = fields.Char(
        index=True,
        help="Client-side outgoing correlation ID (X-MailDesk-Outgoing-ID) used for Sent reconciliation",
    )
    from_addr = fields.Char(index=True)
    to_addrs = fields.Text()
    cc_addrs = fields.Text()
    bcc_addrs = fields.Text()

    subject = fields.Char()
    date = fields.Datetime(index=True)
    sender_display_name = fields.Char()
    preview = fields.Text()
    has_attachments = fields.Boolean(default=False)
    is_read = fields.Boolean(default=False, index=True)
    is_starred = fields.Boolean(default=False, index=True)
    flags = fields.Char()

    # Denormalized tags (CQRS read model optimization)
    tag_ids = fields.Many2many(
        "mail.message.tag",
        "maildesk_index_tag_rel",
        "index_id",
        "tag_id",
        string="Tags",
        help="Denormalized tags for zero-JOIN list queries",
    )

    # Pending operations (projected from email_state for UI responsiveness)
    pending_move_to = fields.Char(
        index=True,
        help="Target folder if move is pending (projected from email_state)",
    )
    pending_delete = fields.Boolean(
        default=False,
        index=True,
        help="True if delete is pending (projected from email_state)",
    )

    # Local pending (sent messages awaiting IMAP confirmation)
    local_pending = fields.Boolean(
        default=False,
        index=True,
        help="Message created locally (e.g. sent mail), pending IMAP reconciliation",
    )

    in_reply_to = fields.Char()
    references_hdr = fields.Text()
    thread_id = fields.Char(index=True)

    sort_ts = fields.Integer(index=True, default=0)
    indexed_at = fields.Datetime(default=fields.Datetime.now, index=True)
    deleted_on_server = fields.Boolean(default=False, index=True)
    ingest_allowed = fields.Boolean(
        default=False,
        index=True,
        help=(
            "When enabled, this SSOT row may be picked up by the MailDesk ingest pipeline "
            "(alias scan -> ingest queue -> mail.thread.message_process). "
            "Backfill/SSOT rebuild keeps this disabled by default."
        ),
    )

    _account_folder_uid_unique = models.Constraint(
        "UNIQUE (account_id, folder, uid)",
        "Message UID must be unique per account/folder",
    )

    @api.model
    def _to_datetime(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            dt = fields.Datetime.to_datetime(value)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @api.model
    def _compute_sort_ts(self, dt):
        if not dt:
            return 0
        try:
            return int(dt.replace(tzinfo=timezone.utc).timestamp())
        except Exception:
            return 0

    @api.model
    def upsert_one(self, vals):
        """
        Idempotent upsert for a single index row.
        Returns the record id on success, False otherwise.
        """
        account_id = vals.get("account_id")
        folder = vals.get("folder")
        uid = vals.get("uid")
        provider = vals.get("provider")
        if not account_id or not folder or uid is None or not provider:
            _logger.warning(
                f"[Index] upsert_one validation failed: "
                f"account_id={account_id}, folder={folder!r}, uid={uid}, provider={provider}"
            )
            return False

        dt = self._to_datetime(vals.get("date"))
        sort_ts = vals.get("sort_ts")
        if not sort_ts:
            sort_ts = self._compute_sort_ts(dt)

        params = {
            "account_id": int(account_id),
            "provider": provider,
            "folder": folder,
            "uid": str(uid),
            "message_id": vals.get("message_id"),
            "outgoing_id": vals.get("outgoing_id"),
            "from_addr": vals.get("from_addr"),
            "to_addrs": vals.get("to_addrs"),
            "cc_addrs": vals.get("cc_addrs"),
            "bcc_addrs": vals.get("bcc_addrs"),
            "subject": vals.get("subject"),
            "date": dt,
            "sender_display_name": vals.get("sender_display_name"),
            "preview": vals.get("preview"),
            "has_attachments": bool(vals.get("has_attachments")),
            "is_read": bool(vals.get("is_read")),
            "is_starred": bool(vals.get("is_starred")),
            "flags": vals.get("flags"),
            "in_reply_to": vals.get("in_reply_to"),
            "references_hdr": vals.get("references_hdr"),
            "thread_id": vals.get("thread_id"),
            "sort_ts": int(sort_ts or 0),
            "indexed_at": vals.get("indexed_at") or fields.Datetime.now(),
            "deleted_on_server": bool(vals.get("deleted_on_server")),
            "ingest_allowed": bool(vals.get("ingest_allowed")),
        }
        params = {k: _strip_nul_chars(v) for k, v in params.items()}

        self.env.cr.execute(
            """
            INSERT INTO maildesk_message_index (
                account_id, provider, folder, uid, message_id, outgoing_id, from_addr, to_addrs,
                cc_addrs, bcc_addrs, subject, date, sender_display_name, preview,
                has_attachments, is_read, is_starred, flags, in_reply_to,
                references_hdr, thread_id, sort_ts, indexed_at, deleted_on_server,
                ingest_allowed, create_date, write_date
            )
            VALUES (
                %(account_id)s, %(provider)s, %(folder)s, %(uid)s, %(message_id)s,
                %(outgoing_id)s, %(from_addr)s, %(to_addrs)s, %(cc_addrs)s, %(bcc_addrs)s,
                %(subject)s, %(date)s, %(sender_display_name)s, %(preview)s,
                %(has_attachments)s, %(is_read)s, %(is_starred)s, %(flags)s,
                %(in_reply_to)s, %(references_hdr)s, %(thread_id)s, %(sort_ts)s,
                %(indexed_at)s, %(deleted_on_server)s, %(ingest_allowed)s, now(), now()
            )
            ON CONFLICT (account_id, folder, uid) DO UPDATE SET
                provider = EXCLUDED.provider,
                message_id = EXCLUDED.message_id,
                outgoing_id = EXCLUDED.outgoing_id,
                from_addr = EXCLUDED.from_addr,
                to_addrs = EXCLUDED.to_addrs,
                cc_addrs = EXCLUDED.cc_addrs,
                bcc_addrs = EXCLUDED.bcc_addrs,
                subject = EXCLUDED.subject,
                date = EXCLUDED.date,
                sender_display_name = EXCLUDED.sender_display_name,
                preview = EXCLUDED.preview,
                has_attachments = EXCLUDED.has_attachments,
                is_read = EXCLUDED.is_read,
                is_starred = EXCLUDED.is_starred,
                flags = EXCLUDED.flags,
                in_reply_to = EXCLUDED.in_reply_to,
                references_hdr = EXCLUDED.references_hdr,
                thread_id = EXCLUDED.thread_id,
                sort_ts = EXCLUDED.sort_ts,
                indexed_at = EXCLUDED.indexed_at,
                deleted_on_server = EXCLUDED.deleted_on_server,
                ingest_allowed = maildesk_message_index.ingest_allowed,
                write_date = now()
            RETURNING id
            """,
            params,
        )
        row = self.env.cr.fetchone()
        return row[0] if row else False

    @api.model
    def upsert_one_with_inserted(self, vals):
        """
        Upsert a single index row, returning (record_id, inserted).

        This preserves the observable behavior of `upsert_one()` (same fields
        updated on conflict), but additionally exposes whether the row was
        newly created. This is used to make desktop notifications deterministic
        and deduplicated by SSOT id.
        """
        account_id = vals.get("account_id")
        folder = vals.get("folder")
        uid = vals.get("uid")
        provider = vals.get("provider")
        if not account_id or not folder or uid is None or not provider:
            _logger.warning(
                f"[Index] upsert_one_with_inserted validation failed: "
                f"account_id={account_id}, folder={folder!r}, uid={uid}, provider={provider}"
            )
            return False, False

        dt = self._to_datetime(vals.get("date"))
        sort_ts = vals.get("sort_ts")
        if not sort_ts:
            sort_ts = self._compute_sort_ts(dt)

        params = {
            "account_id": int(account_id),
            "provider": provider,
            "folder": folder,
            "uid": str(uid),
            "message_id": vals.get("message_id"),
            "outgoing_id": vals.get("outgoing_id"),
            "from_addr": vals.get("from_addr"),
            "to_addrs": vals.get("to_addrs"),
            "cc_addrs": vals.get("cc_addrs"),
            "bcc_addrs": vals.get("bcc_addrs"),
            "subject": vals.get("subject"),
            "date": dt,
            "sender_display_name": vals.get("sender_display_name"),
            "preview": vals.get("preview"),
            "has_attachments": bool(vals.get("has_attachments")),
            "is_read": bool(vals.get("is_read")),
            "is_starred": bool(vals.get("is_starred")),
            "flags": vals.get("flags"),
            "in_reply_to": vals.get("in_reply_to"),
            "references_hdr": vals.get("references_hdr"),
            "thread_id": vals.get("thread_id"),
            "sort_ts": int(sort_ts or 0),
            "indexed_at": vals.get("indexed_at") or fields.Datetime.now(),
            "deleted_on_server": bool(vals.get("deleted_on_server")),
            "ingest_allowed": bool(vals.get("ingest_allowed")),
        }
        params = {k: _strip_nul_chars(v) for k, v in params.items()}

        # Step 1: try insert only (no conflict update), to detect inserted deterministically.
        self.env.cr.execute(
            """
            INSERT INTO maildesk_message_index (
                account_id, provider, folder, uid, message_id, outgoing_id, from_addr, to_addrs,
                cc_addrs, bcc_addrs, subject, date, sender_display_name, preview,
                has_attachments, is_read, is_starred, flags, in_reply_to,
                references_hdr, thread_id, sort_ts, indexed_at, deleted_on_server,
                ingest_allowed, create_date, write_date
            )
            VALUES (
                %(account_id)s, %(provider)s, %(folder)s, %(uid)s, %(message_id)s,
                %(outgoing_id)s, %(from_addr)s, %(to_addrs)s, %(cc_addrs)s, %(bcc_addrs)s,
                %(subject)s, %(date)s, %(sender_display_name)s, %(preview)s,
                %(has_attachments)s, %(is_read)s, %(is_starred)s, %(flags)s,
                %(in_reply_to)s, %(references_hdr)s, %(thread_id)s, %(sort_ts)s,
                %(indexed_at)s, %(deleted_on_server)s, %(ingest_allowed)s, now(), now()
            )
            ON CONFLICT (account_id, folder, uid) DO NOTHING
            RETURNING id
            """,
            params,
        )
        row = self.env.cr.fetchone()
        if row:
            return row[0], True

        # Step 2: conflict -> update existing row with the same semantics as upsert_one()
        self.env.cr.execute(
            """
            UPDATE maildesk_message_index
               SET provider = %(provider)s,
                   message_id = %(message_id)s,
                   outgoing_id = %(outgoing_id)s,
                   from_addr = %(from_addr)s,
                   to_addrs = %(to_addrs)s,
                   cc_addrs = %(cc_addrs)s,
                   bcc_addrs = %(bcc_addrs)s,
                   subject = %(subject)s,
                   date = %(date)s,
                   sender_display_name = %(sender_display_name)s,
                   preview = %(preview)s,
                   has_attachments = %(has_attachments)s,
                   is_read = %(is_read)s,
                   is_starred = %(is_starred)s,
                   flags = %(flags)s,
                   in_reply_to = %(in_reply_to)s,
                   references_hdr = %(references_hdr)s,
                   thread_id = %(thread_id)s,
                   sort_ts = %(sort_ts)s,
                   indexed_at = %(indexed_at)s,
                   deleted_on_server = %(deleted_on_server)s,
                   write_date = now()
             WHERE account_id = %(account_id)s
               AND folder = %(folder)s
               AND uid = %(uid)s
            RETURNING id
            """,
            params,
        )
        row = self.env.cr.fetchone()
        return (row[0] if row else False), False

    def action_reenqueue_for_ingestion(self):
        """Admin action: Re-enqueue message for ingestion"""
        adapter = IngestQueueAdapter(self.env)
        enqueue = EnqueueIngestForMessageIndex(adapter)

        for record in self:
            if not record.deleted_on_server:
                record.write({"ingest_allowed": True})
                enqueue.execute(EnqueueIngestForMessageIndexParams(index_id=record.id))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": f"{len(self)} message(s) re-queued for ingestion",
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def update_state_projection(
        self,
        account_id,
        folder,
        uid,
        is_read=None,
        is_starred=None,
        pending_move_to=None,
        pending_delete=None,
        index_id=None,
    ):
        """
        CQRS projection: Update denormalized state fields from UI actions.

        This is called immediately after writing to maildesk.email_state
        to keep the read model in sync with pending operations.

        Args:
            index_id: Optional record ID to update directly (bypasses triplet search)
        """
        rec = None
        if index_id:
            rec = self.browse(index_id)
            if not rec.exists():
                rec = None

        if not rec:
            domain = [
                ("account_id", "=", account_id),
                ("folder", "=", folder),
                ("uid", "=", str(uid)),
            ]

            _logger.info(
                f"[MessageIndex] update_state_projection: searching domain={domain}"
            )

            rec = self.search(domain, limit=1)

        if not rec:
            _logger.warning(
                f"[MessageIndex] NOT FOUND: account={account_id}, "
                f"folder={folder}, uid={uid}, index_id={index_id}"
            )
            return False

        vals = {}
        if is_read is not None:
            vals["is_read"] = bool(is_read)
        if is_starred is not None:
            vals["is_starred"] = bool(is_starred)
        if pending_move_to is not None:
            vals["pending_move_to"] = pending_move_to
        if pending_delete is not None:
            vals["pending_delete"] = bool(pending_delete)

        if vals:
            _logger.info(f"[MessageIndex] UPDATING id={rec.id} with vals={vals}")
            rec.write(vals)
        else:
            _logger.info(f"[MessageIndex] NO VALUES to update for id={rec.id}")

        return True

    @api.model
    def update_tags(self, account_id, folder, uid, tag_ids):
        """
        CQRS projection: Update denormalized tags from UI action.

        Args:
            tag_ids: List of tag IDs to assign (replaces all existing)

        Returns:
            dict: Updated tag objects if found, None if not found
        """
        domain = [
            ("account_id", "=", account_id),
            ("folder", "=", folder),
            ("uid", "=", str(uid)),
        ]
        rec = self.search(domain, limit=1)
        if not rec:
            return None

        # Replace all tags (Odoo command: (6, 0, ids))
        rec.write({"tag_ids": [(6, 0, tag_ids)]})

        # Invalidate cache for this message to ensure fresh reads
        self.env["maildesk.ui_cache"].invalidate_message_cache(account_id, folder, uid)

        # Return actual tag objects for verification
        return {
            "index_id": rec.id,
            "tags": [
                {"id": t.id, "name": t.name, "color": t.color} for t in rec.tag_ids
            ],
        }

    @api.model
    def find_by_triplet(self, account_id, folder, uid):
        """Helper to find message_index record by account/folder/uid triplet."""
        return self.search(
            [
                ("account_id", "=", account_id),
                ("folder", "=", folder),
                ("uid", "=", str(uid)),
            ],
            limit=1,
        )

    # ------------------------------------------------------------------
    # Outbound → provider reconciliation (SSOT correctness)
    # ------------------------------------------------------------------

    @api.model
    def _norm_folder_key(self, folder: str) -> str:
        return (folder or "").strip().lower()

    @api.model
    def _build_provider_update_vals(self, provider_message_data: dict | None) -> dict:
        if not provider_message_data:
            return {}

        vals: dict = {}
        passthrough_fields = [
            "message_id",
            "outgoing_id",
            "from_addr",
            "to_addrs",
            "cc_addrs",
            "bcc_addrs",
            "subject",
            "sender_display_name",
            "preview",
            "has_attachments",
            "is_read",
            "is_starred",
            "flags",
            "in_reply_to",
            "references_hdr",
            "thread_id",
            "deleted_on_server",
        ]
        for key in passthrough_fields:
            if (
                key in provider_message_data
                and provider_message_data.get(key) is not None
            ):
                vals[key] = provider_message_data.get(key)

        if (
            "date" in provider_message_data
            and provider_message_data.get("date") is not None
        ):
            dt = self._to_datetime(provider_message_data.get("date"))
            vals["date"] = dt
            if not provider_message_data.get("sort_ts"):
                vals["sort_ts"] = self._compute_sort_ts(dt)

        if (
            "sort_ts" in provider_message_data
            and provider_message_data.get("sort_ts") is not None
        ):
            try:
                vals["sort_ts"] = int(provider_message_data.get("sort_ts") or 0)
            except Exception:
                pass

        return vals

    @api.model
    def _delete_conflicting_triplet_if_safe(
        self,
        *,
        account_id: int,
        provider_folder: str,
        provider_uid: str,
        keep_id: int,
        expected_outgoing_id: str | None,
        expected_provider: str | None,
    ) -> bool:
        conflict = self.search(
            [
                ("account_id", "=", int(account_id)),
                ("folder", "=", provider_folder),
                ("uid", "=", str(provider_uid)),
                ("id", "!=", int(keep_id)),
            ],
            limit=1,
        )
        if not conflict:
            return True

        if expected_provider and conflict.provider != expected_provider:
            _logger.error(
                "[SSOT] Outbound confirm conflict: triplet belongs to other provider "
                "(keep_id=%s conflict_id=%s provider=%s expected=%s)",
                keep_id,
                conflict.id,
                conflict.provider,
                expected_provider,
            )
            return False

        if conflict.local_pending:
            _logger.error(
                "[SSOT] Outbound confirm conflict: triplet belongs to another local_pending row "
                "(keep_id=%s conflict_id=%s)",
                keep_id,
                conflict.id,
            )
            return False

        if (
            expected_outgoing_id
            and conflict.outgoing_id
            and conflict.outgoing_id != expected_outgoing_id
        ):
            _logger.error(
                "[SSOT] Outbound confirm conflict: triplet belongs to different outgoing_id "
                "(keep_id=%s conflict_id=%s conflict_outgoing_id=%s expected=%s)",
                keep_id,
                conflict.id,
                conflict.outgoing_id,
                expected_outgoing_id,
            )
            return False

        _logger.warning(
            "[SSOT] Removing conflicting index row to preserve stable index_id for outbound confirmation "
            "(keep_id=%s delete_id=%s folder=%s uid=%s)",
            keep_id,
            conflict.id,
            provider_folder,
            provider_uid,
        )
        conflict.unlink()
        return True

    @api.model
    def confirm_outbound_delivery(
        self,
        *,
        account_id: int,
        outgoing_id: str,
        provider: str,
        provider_uid: str,
        provider_folder: str,
        provider_message_data: dict | None = None,
    ) -> bool:
        """
        Confirm a SSOT-on-send local_pending row in-place using outgoing_id.

        Contract (fail-closed):
        - Matches exactly one row: (account_id, provider, local_pending=True, outgoing_id)
        - Confirms only when provider_folder matches the pending row's folder (prevents
          accidental confirmation from other folders like ALL_MAIL/INBOX).
        - Preserves `id` (index_id) and clears local_pending.
        """
        if (
            not account_id
            or not outgoing_id
            or not provider
            or not provider_uid
            or not provider_folder
        ):
            return False

        pending_rows = self.search(
            [
                ("account_id", "=", int(account_id)),
                ("provider", "=", provider),
                ("local_pending", "=", True),
                ("outgoing_id", "=", outgoing_id),
            ],
            limit=2,
        )
        if not pending_rows:
            return False
        if len(pending_rows) > 1:
            _logger.error(
                "[SSOT] Multiple local_pending rows for outgoing_id=%s account_id=%s provider=%s; refusing to confirm",
                outgoing_id,
                account_id,
                provider,
            )
            return False

        pending = pending_rows[0]
        pending_folder = pending.folder or ""
        if self._norm_folder_key(pending_folder) != self._norm_folder_key(
            provider_folder
        ):
            _logger.info(
                "[SSOT] Outbound confirm skipped due to folder mismatch: outgoing_id=%s pending_folder=%r provider_folder=%r",
                outgoing_id,
                pending_folder,
                provider_folder,
            )
            return False

        if not self._delete_conflicting_triplet_if_safe(
            account_id=int(account_id),
            provider_folder=provider_folder,
            provider_uid=str(provider_uid),
            keep_id=pending.id,
            expected_outgoing_id=outgoing_id,
            expected_provider=provider,
        ):
            return False

        vals = {
            "uid": str(provider_uid),
            "folder": provider_folder,
            "local_pending": False,
        }
        vals.update(self._build_provider_update_vals(provider_message_data))
        vals.setdefault("outgoing_id", outgoing_id)

        pending.write(vals)
        return True

    @api.model
    def confirm_outbound_delivery_by_message_id(
        self,
        *,
        account_id: int,
        provider: str,
        provider_uid: str,
        provider_folder: str,
        message_id: str,
        message_from: str | None = None,
        provider_message_data: dict | None = None,
        max_age_hours: int = 72,
    ) -> bool:
        """
        Fallback confirmation when outgoing_id is missing on the provider message.

        Safety guards:
        - Confirms only local_pending=True rows
        - Requires Message-ID match after normalization
        - Requires provider_folder matches pending folder (prevents INBOX/ALL_MAIL accidents)
        - Requires sender match when available (account email == message_from)
        - Requires recent pending row (max_age_hours)
        """
        if (
            not account_id
            or not provider
            or not provider_uid
            or not provider_folder
            or not message_id
        ):
            return False

        # Keep domain tight: pending items should be few; also folder match is mandatory.
        candidates = self.search(
            [
                ("account_id", "=", int(account_id)),
                ("provider", "=", provider),
                ("local_pending", "=", True),
                ("folder", "=", provider_folder),
            ]
        )
        if not candidates:
            return False

        mid_norm = norm_msgid(message_id)
        if not mid_norm:
            return False

        matched = candidates.filtered(lambda r: norm_msgid(r.message_id) == mid_norm)
        if not matched:
            return False
        if len(matched) > 1:
            _logger.error(
                "[SSOT] Multiple local_pending rows match Message-ID fallback: account_id=%s provider=%s folder=%s mid=%s",
                account_id,
                provider,
                provider_folder,
                mid_norm,
            )
            return False

        pending = matched[0]

        if message_from:
            a = (pending.from_addr or "").strip().lower()
            b = (message_from or "").strip().lower()
            if a and b and a != b:
                return False

        if max_age_hours and pending.date:
            now = fields.Datetime.now()
            try:
                age_limit = now - timedelta(hours=int(max_age_hours))
                if pending.date < age_limit:
                    return False
            except Exception:
                pass

        if not self._delete_conflicting_triplet_if_safe(
            account_id=int(account_id),
            provider_folder=provider_folder,
            provider_uid=str(provider_uid),
            keep_id=pending.id,
            expected_outgoing_id=pending.outgoing_id,
            expected_provider=provider,
        ):
            return False

        vals = {
            "uid": str(provider_uid),
            "folder": provider_folder,
            "local_pending": False,
        }
        vals.update(self._build_provider_update_vals(provider_message_data))
        vals.setdefault("message_id", message_id)

        pending.write(vals)
        return True

    @api.model
    def reconcile_thread_id_from_reply(
        self,
        *,
        account_id: int,
        provider: str,
        thread_id: str,
        in_reply_to: str,
    ) -> int:
        """
        Best-effort threading reconciliation for providers with native thread IDs (Gmail/Outlook).

        Why:
        - SSOT-on-send creates local_pending rows immediately for UX.
        - For Gmail, those rows initially use Message-ID-derived thread_id (because the Gmail threadId is unknown).
        - When an incoming reply arrives (with In-Reply-To + provider threadId), we update the parent SSOT row(s)
          to the provider's threadId so the UI can show a single conversation.

        Contract:
        - Never creates rows.
        - Only updates existing rows matching the parent Message-ID.
        - Returns number of SSOT rows updated.
        """
        if not account_id or not provider or not thread_id or not in_reply_to:
            return 0

        parent_mid = norm_msgid(in_reply_to)
        if not parent_mid:
            return 0

        candidates = self.search(
            [
                ("account_id", "=", int(account_id)),
                ("provider", "=", str(provider)),
                ("message_id", "!=", False),
            ]
        )
        recs = candidates.filtered(lambda r: norm_msgid(r.message_id) == parent_mid)
        if not recs:
            return 0

        to_update = recs.filtered(lambda r: (r.thread_id or "") != str(thread_id))
        if not to_update:
            return 0

        to_update.write({"thread_id": str(thread_id)})
        return len(to_update)

    @api.model
    def touch_existing_outgoing_delivery(
        self,
        *,
        account_id: int,
        provider: str,
        provider_folder: str,
        outgoing_id: str,
        provider_message_data: dict | None = None,
    ) -> int | bool:
        """
        If a non-pending SSOT row already exists for (account, provider, folder, outgoing_id),
        update it in-place and return its id. Used to avoid creating additional duplicates
        when providers expose multiple Sent copies with the same outgoing_id.
        """
        if not account_id or not provider or not provider_folder or not outgoing_id:
            return False

        recs = self.search(
            [
                ("account_id", "=", int(account_id)),
                ("provider", "=", provider),
                ("folder", "=", provider_folder),
                ("outgoing_id", "=", outgoing_id),
                ("local_pending", "=", False),
            ],
            limit=2,
        )
        if not recs:
            return False
        if len(recs) > 1:
            _logger.error(
                "[SSOT] Multiple confirmed rows for outgoing_id=%s account_id=%s provider=%s folder=%s; skipping insert to avoid more duplicates",
                outgoing_id,
                account_id,
                provider,
                provider_folder,
            )
            return True

        rec = recs[0]
        vals = {"local_pending": False}
        vals.update(self._build_provider_update_vals(provider_message_data))
        if vals:
            rec.write(vals)
        return int(rec.id)
