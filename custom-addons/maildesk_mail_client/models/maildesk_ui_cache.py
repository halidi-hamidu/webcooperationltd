# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
MailDesk UI Cache Model.

Provides ephemeral caching layer for message metadata and bodies with TTL-based
expiration. Supports advisory locks for concurrent write safety and canonical
index resolution for Gmail/Outlook message deduplication.
"""

import hashlib
import json
import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

from ..application.use_cases import (
    PrepareForward,
    PrepareForwardParams,
    PrepareReply,
    PrepareReplyParams,
)
from ..infrastructure.adapters.composer_adapter import ComposerAdapter

_logger = logging.getLogger(__name__)


class MailDeskUICache(models.Model):
    """
    UI cache for message metadata and bodies.

    Features:
    - TTL-based expiration
    - JSONB storage for flexible schema
    - Advisory locks for concurrent write safety
    - Canonical index resolution (Gmail/Outlook deduplication)
    """

    _name = "maildesk.ui_cache"
    _description = "MailDesk: UI Cache (TTL)"
    _rec_name = "id"
    _order = "id desc"

    index_id = fields.Many2one(
        comodel_name="maildesk.message_index",
        required=True,
        index=True,
        ondelete="cascade",
    )
    json_cache = fields.Json()
    json_cache_until = fields.Datetime(index=True)
    cache_until = fields.Datetime(
        index=True,
        default=lambda self: fields.Datetime.now() + relativedelta(hours=1),
    )

    _index_id_unique = models.Constraint(
        "UNIQUE (index_id)",
        "One cache entry per indexed message",
    )

    _CACHE_LOCK_NAMESPACE = 48231

    @api.model
    def acquire_index_lock(self, index_id: int) -> None:
        """
        Acquire transaction-level advisory lock for cache mutations by index_id.

        Args:
            index_id: message_index record ID

        Note:
            Lock is automatically released at transaction end.
        """
        try:
            idx = int(index_id or 0)
        except (TypeError, ValueError):
            return

        if idx <= 0:
            return

        lock_key = (self._CACHE_LOCK_NAMESPACE << 32) | (idx & 0xFFFFFFFF)
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

    @api.model
    def acquire_message_lock(self, account_id, provider, uid) -> None:
        """
        Acquire transaction-level advisory lock for cache mutations by provider UID.

        Used for Gmail/Outlook messages to serialize writes across folders
        (same message can appear in multiple virtual folders).

        Args:
            account_id: mailbox.account ID
            provider: Provider type ('gmail' or 'outlook')
            uid: Provider-specific message UID

        Note:
            Lock key derived from blake2b hash of account:provider:uid triplet.
        """
        if not account_id or not provider or not uid:
            return

        key_src = f"{int(account_id)}:{provider}:{uid}"
        digest = hashlib.blake2b(key_src.encode("utf-8"), digest_size=8).digest()
        lock_key = int.from_bytes(digest, byteorder="big", signed=False)
        lock_key = lock_key & 0x7FFFFFFFFFFFFFFF
        self.env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (int(lock_key),))

    @api.model
    def acquire_cache_lock_for_index(self, index_id: int) -> None:
        """
        Acquire appropriate advisory lock based on provider type.

        For Gmail/Outlook: locks on provider UID (cross-folder deduplication)
        For IMAP/others: locks on index_id directly
        Exception: Drafts folder always uses index_id lock

        Args:
            index_id: message_index record ID
        """
        if not index_id:
            return

        Index = self.env["maildesk.message_index"].sudo()
        rec = Index.browse(int(index_id))

        if not rec or not rec.exists():
            self.acquire_index_lock(index_id)
            return

        if (
            rec.provider in ("gmail", "outlook")
            and rec.uid
            and not self._is_drafts_folder(rec.account_id.id, rec.folder)
        ):
            self.acquire_message_lock(rec.account_id.id, rec.provider, rec.uid)
            return

        self.acquire_index_lock(index_id)

    @api.model
    def _is_drafts_folder(self, account_id: int, folder_name: str) -> bool:
        """
        Check if folder is a drafts folder.

        Args:
            account_id: mailbox.account ID
            folder_name: Folder name to check

        Returns:
            bool: True if folder is drafts type
        """
        if not account_id or not folder_name:
            return False

        Folder = self.env["mailbox.folder"].sudo()
        folder = Folder.search(
            [
                ("account_id", "=", int(account_id)),
                "|",
                ("imap_name", "=", folder_name),
                ("name", "=", folder_name),
            ],
            limit=1,
        )

        if folder and getattr(folder, "folder_type", None) == "drafts":
            return True

        return (folder_name or "").strip().lower() in {"drafts", "draft"}

    @api.model
    def resolve_canonical_index_id(self, index_id: int) -> int:
        """
        Resolve canonical cache index_id for Gmail/Outlook messages.

        Gmail/Outlook messages may exist in multiple virtual folders (labels)
        with different index IDs. This resolves them to a single canonical ID
        (preferring ALL_MAIL folder, otherwise oldest index_id).

        Args:
            index_id: Input message_index ID

        Returns:
            int: Canonical index_id for caching (may equal input)

        Note:
            IMAP messages and drafts always return their own ID unchanged.
        """
        if not index_id:
            return index_id

        Index = self.env["maildesk.message_index"].sudo()
        rec = Index.browse(int(index_id))

        if not rec or not rec.exists():
            return int(index_id)

        if rec.provider not in ("gmail", "outlook") or not rec.uid:
            return int(rec.id)

        if self._is_drafts_folder(rec.account_id.id, rec.folder):
            return int(rec.id)

        canonical = Index.search(
            [
                ("account_id", "=", rec.account_id.id),
                ("provider", "=", rec.provider),
                ("folder", "=", "ALL_MAIL"),
                ("uid", "=", rec.uid),
            ],
            order="id asc",
            limit=1,
        )

        if not canonical:
            canonical = Index.search(
                [
                    ("account_id", "=", rec.account_id.id),
                    ("provider", "=", rec.provider),
                    ("uid", "=", rec.uid),
                ],
                order="id asc",
                limit=1,
            )

        return int(canonical.id) if canonical else int(rec.id)

    @api.model
    def fetch_for_index_records(self, index_records):
        """
        Fetch valid cache entries for given message_index records.

        Args:
            index_records: maildesk.message_index recordset or list of IDs

        Returns:
            dict: Mapping {index_id: cache_record} for valid (non-expired) entries
        """
        if not index_records:
            return {}

        ids = []
        if isinstance(index_records, list):
            if index_records and hasattr(index_records[0], "id"):
                ids = [r.id for r in index_records]
            else:
                ids = index_records
        else:
            ids = index_records.ids

        now = fields.Datetime.now()
        cache_recs = self.search(
            [
                ("index_id", "in", ids),
                ("json_cache_until", ">=", now),
            ]
        )
        return {rec.index_id.id: rec for rec in cache_recs}

    @api.model
    def _upsert_json_cache_patch(self, index_id: int, json_patch: dict, expire_at):
        """
        Upsert JSONB cache patch for index_id.

        Merges json_patch into existing json_cache using jsonb concatenation.
        Uses SQL UPSERT to avoid race conditions.

        Args:
            index_id: message_index record ID
            json_patch: Dict to merge into existing cache
            expire_at: Expiration datetime for this cache entry

        Returns:
            maildesk.ui_cache record (False if failed)

        Important:
            Caller MUST hold advisory lock via acquire_cache_lock_for_index.
            This method does NOT acquire locks to avoid double-locking.
        """
        if not index_id:
            return self.browse(False)

        index_id = self.resolve_canonical_index_id(index_id)
        patch_json = json.dumps(json_patch or {})
        uid = self.env.uid

        self.env.cr.execute(
            """
            INSERT INTO maildesk_ui_cache (
                index_id, json_cache, json_cache_until, cache_until,
                create_uid, write_uid, create_date, write_date
            )
            VALUES (
                %s, %s::jsonb, %s, %s,
                %s, %s, now(), now()
            )
            ON CONFLICT (index_id) DO UPDATE SET
                json_cache = COALESCE(maildesk_ui_cache.json_cache, '{}'::jsonb) || EXCLUDED.json_cache,
                json_cache_until = EXCLUDED.json_cache_until,
                cache_until = EXCLUDED.cache_until,
                write_uid = EXCLUDED.write_uid,
                write_date = now()
            RETURNING id
            """,
            (int(index_id), patch_json, expire_at, expire_at, uid, uid),
        )
        row = self.env.cr.fetchone()
        cache_id = row[0] if row else False
        return self.browse(cache_id)

    @api.model
    def upsert_list_cache(self, index_id, payload, ttl_minutes=60):
        """
        Upsert list view cache (metadata without body).

        Args:
            index_id: message_index record ID
            payload: Dict with list view metadata
            ttl_minutes: Cache TTL in minutes (default 60)

        Returns:
            maildesk.ui_cache record
        """
        expire_at = fields.Datetime.now() + relativedelta(minutes=ttl_minutes)
        return self._upsert_json_cache_patch(index_id, payload or {}, expire_at)

    @api.model
    def fetch_body_cache(self, index_id):
        """
        Fetch cached message body for detail view.

        Args:
            index_id: message_index record ID

        Returns:
            dict or None: {body_html, body_text, attachments} if cache valid, else None
        """
        if not index_id:
            return None

        now = fields.Datetime.now()
        cache = self.search(
            [
                ("index_id", "=", index_id),
                ("json_cache_until", ">=", now),
            ],
            limit=1,
        )

        if not cache or not cache.json_cache:
            return None

        body_data = cache.json_cache.get("body")
        if not body_data:
            return None
        if body_data.get("body_html") is None:
            return None

        return {
            "body_html": body_data.get("body_html"),
            "body_text": body_data.get("body_text"),
            "attachments": body_data.get("attachments", []),
        }

    @api.model
    def upsert_body_cache(
        self, index_id, body_html, body_text=None, attachments=None, ttl_days=None
    ):
        """
        Upsert message body cache after fetching from provider.

        Args:
            index_id: message_index record ID
            body_html: HTML body content
            body_text: Plain text fallback
            attachments: List of attachment dicts
            ttl_days: Cache retention in days (from config if None)

        Returns:
            maildesk.ui_cache record
        """
        if ttl_days is None:
            ttl_days = int(
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("maildesk.cache_retention_days", "30")
            )

        expire_at = fields.Datetime.now() + relativedelta(days=ttl_days)

        body_payload = {
            "body_html": body_html,
            "body_text": body_text,
            "attachments": attachments or [],
        }
        return self._upsert_json_cache_patch(
            index_id, {"body": body_payload}, expire_at
        )

    @api.model
    def _cron_cleanup_expired_cache(self):
        """
        Cleanup expired cache entries (cron job).

        Deletes cache entries past their cache_until timestamp.
        SSOT (message_index) remains untouched - expired entries
        will be refetched from provider on next access.

        Returns:
            dict: {deleted_count: int}
        """
        now = fields.Datetime.now()
        expired = self.sudo().search([("cache_until", "<", now)])

        count = len(expired)
        if count > 0:
            expired.unlink()
            _logger.info("Deleted %d expired cache entries", count)
        else:
            _logger.info("No expired cache entries to clean")

        return {"deleted_count": count}

    @api.model
    def prepare_reply(self, msg_key, reply_all=False):
        """
        Prepare reply/reply-all composer data (RPC endpoint).

        Args:
            msg_key: Message identifier (index_id or cache UID)
            reply_all: Include all recipients if True

        Returns:
            dict: Composer data with recipients, subject, body template
        """
        adapter = ComposerAdapter(self.env)
        use_case = PrepareReply(adapter)
        params = PrepareReplyParams(msg_key=msg_key, reply_all=reply_all)
        return use_case.execute(params)

    @api.model
    def prepare_forward(self, msg_key):
        """
        Prepare forward composer data (RPC endpoint).

        Args:
            msg_key: Message identifier (index_id or cache UID)

        Returns:
            dict: Composer data with original message quoted and attachments
        """
        adapter = ComposerAdapter(self.env)
        use_case = PrepareForward(adapter)
        params = PrepareForwardParams(msg_key=msg_key)
        return use_case.execute(params)

    @api.model
    def invalidate_message_cache(self, account_id, folder, uid):
        """
        Invalidate cache for a specific message to force fresh fetch.

        Args:
            account_id: mailbox.account ID
            folder: Folder name
            uid: Message UID

        Returns:
            bool: True if cache was invalidated
        """
        if not account_id or not uid:
            return False

        Index = self.env["maildesk.message_index"].sudo()
        domain = [
            ("account_id", "=", int(account_id)),
            ("folder", "=", folder),
            ("uid", "=", str(uid)),
        ]
        index_rec = Index.search(domain, limit=1)
        if not index_rec:
            return False

        # Find and delete cache entry
        cache = self.search([("index_id", "=", index_rec.id)])
        if cache:
            cache.unlink()
            return True

        return False
