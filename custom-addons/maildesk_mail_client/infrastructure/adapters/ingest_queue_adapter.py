# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Ingest Queue Adapter.

Implements infrastructure integration for Ingest Queue Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

import base64
import logging
from typing import List, Optional

from googleapiclient.errors import HttpError
from psycopg2 import IntegrityError
from odoo import fields

from ...application.services.imap_client_service import build_authenticated_imap_client
from ...application.use_cases.ingest_queue import (
    MailMessageInfo,
    QueueContext,
    StuckQueueInfo,
)
from ..providers.gmail.auth import gmail_build_service
from ..providers.outlook.client_factory import get_outlook_client

_logger = logging.getLogger(__name__)

LOCK_KEY = "maildesk_ingest_queue_lock"


class IngestQueueAdapter:
    def __init__(self, env):
        self.env = env

    def now(self):
        return fields.Datetime.now()

    def _queue(self):
        return self.env["maildesk.ingest_queue"].sudo()

    def _index(self):
        return self.env["maildesk.message_index"].sudo()

    def lock_acquire(self) -> bool:
        # Transaction-scoped lock: auto-released on commit/rollback, no explicit unlock needed.
        self.env.cr.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
            (LOCK_KEY,),
        )
        return bool(self.env.cr.fetchone()[0])

    def lock_release(self) -> None:
        # No-op for xact locks (released automatically).
        return None

    def index_exists(self, index_id: int) -> bool:
        return bool(self._index().browse(int(index_id)).exists())

    def queue_find_by_index(self, index_id: int):
        rec = self._queue().search([("index_id", "=", int(index_id))], limit=1)
        return rec.id if rec else None

    def queue_create(self, index_id: int, priority: int):
        """
        Create queue entry with duplicate protection.

        Uses savepoint to handle unique constraint violations gracefully.
        If duplicate exists, returns existing queue_id instead of failing.
        """
        # Fast path: check if already exists before attempting create
        existing = self._queue().search([("index_id", "=", int(index_id))], limit=1)
        if existing:
            return existing.id

        # Attempt create with savepoint protection
        try:
            with self.env.cr.savepoint():
                rec = self._queue().create(
                    {
                        "index_id": int(index_id),
                        "state": "pending",
                        "priority": int(priority or 10),
                    }
                )
                return rec.id
        except IntegrityError:
            # Unique constraint violation - another process created it between check and create
            # This is expected in concurrent scenarios, fetch the record that won the race
            rec = self._queue().search([("index_id", "=", int(index_id))], limit=1)
            return rec.id if rec else None
        except Exception as e:
            # Unexpected error
            _logger.warning(
                f"Unexpected error creating queue for index {index_id}: {e}"
            )
            return None

    def enqueue(self, vals: dict) -> Optional[int]:
        """
        P0-3 Compatibility method for old bootstrap/backfill logic.
        Auto-creates message_index stub and enqueues it.

        Args:
            vals: dict with account_id, folder_id, uid, provider
        """
        Index = self.env["maildesk.message_index"].sudo()
        Folder = self.env["mailbox.folder"].sudo().browse(int(vals["folder_id"]))

        # Basic validation
        if not Folder.exists():
            _logger.error("Folder %s not found in enqueue", vals.get("folder_id"))
            return None

        # Upsert stub into message_index
        index_id = Index.upsert_one(
            {
                "account_id": int(vals["account_id"]),
                "provider": vals["provider"],
                "folder": Folder.imap_name or Folder.name,
                "uid": str(vals["uid"]),
                "subject": "Indexed – awaiting metadata (message will appear shortly)",
                "date": fields.Datetime.now(),
            }
        )

        if index_id:
            return self.queue_create(index_id, priority=vals.get("priority", 10))

        # Upsert failed - log for diagnosis
        _logger.error(
            f"[Ingest] Failed to upsert message_index for "
            f"folder_id={vals.get('folder_id')}, uid={vals.get('uid')}. "
            f"Check folder existence and message_index validation."
        )
        return None

    # ------------------------------------------------------------------
    # Eligibility / alias detection
    # ------------------------------------------------------------------

    def should_ingest(self, index_id: int) -> bool:
        idx = self._index().browse(int(index_id))
        if not idx.exists():
            return False
        if idx.deleted_on_server:
            return False
        if not getattr(idx, "ingest_allowed", False):
            return False
        if not self._is_incoming_eligible(idx):
            return False

        aliases = self._get_aliases()
        condition, params = self._alias_condition(aliases)

        self.env.cr.execute(
            f"SELECT 1 FROM maildesk_message_index WHERE id = %s AND ({condition})",
            (idx.id,) + params,
        )
        return bool(self.env.cr.fetchone())

    def _get_aliases(self):
        Alias = self.env["mail.alias"].sudo()
        return Alias.search(
            [
                ("alias_name", "!=", False),
                ("alias_model_id", "!=", False),
                ("alias_domain_id", "!=", False),
            ]
        )

    def _alias_condition(self, aliases):
        pattern_openerp = "%openerp-%"

        if not aliases:
            condition = (
                "(COALESCE(message_id, '') ILIKE %s "
                " OR COALESCE(in_reply_to, '') ILIKE %s "
                " OR COALESCE(references_hdr, '') ILIKE %s)"
            )
            params = (pattern_openerp, pattern_openerp, pattern_openerp)
            return condition, params

        full_emails = []
        localparts = []
        for alias in aliases:
            alias_name = (alias.alias_name or "").lower()
            domain = (alias.alias_domain_id.name or "").lower()
            if not alias_name or not domain:
                continue
            full_emails.append(f"%{alias_name}@{domain}%")
            localparts.append(f"%{alias_name}@")

        if not full_emails:
            condition = (
                "(COALESCE(message_id, '') ILIKE %s "
                " OR COALESCE(in_reply_to, '') ILIKE %s "
                " OR COALESCE(references_hdr, '') ILIKE %s)"
            )
            params = (pattern_openerp, pattern_openerp, pattern_openerp)
            return condition, params

        full_pattern = "|".join(full_emails)
        localpart_pattern = "|".join(localparts)

        condition = (
            "(COALESCE(message_id, '') ILIKE %s "
            " OR COALESCE(in_reply_to, '') ILIKE %s "
            " OR COALESCE(references_hdr, '') ILIKE %s "
            " OR LOWER(to_addrs || ',' || COALESCE(cc_addrs, '')) SIMILAR TO %s "
            " OR ("
            "     (to_addrs ILIKE '%%@%%' OR COALESCE(cc_addrs, '') ILIKE '%%@%%')"
            "     AND ("
            "         LOWER(to_addrs) SIMILAR TO %s"
            "         OR LOWER(COALESCE(cc_addrs, '')) SIMILAR TO %s"
            "     )"
            " ))"
        )

        params = (
            pattern_openerp,
            pattern_openerp,
            pattern_openerp,
            f"%({full_pattern})%",
            f"%({localpart_pattern})%",
            f"%({localpart_pattern})%",
        )
        return condition, params

    def _get_folder_type_for_index(self, idx):
        AccountFolder = self.env["mailbox.folder"].sudo()
        folder = AccountFolder.search(
            [
                ("account_id", "=", idx.account_id.id),
                ("imap_name", "=", idx.folder),
            ],
            limit=1,
        )
        return folder.folder_type if folder else "other"

    def _is_incoming_eligible(self, idx):
        account = idx.account_id
        ftype = self._get_folder_type_for_index(idx)
        if ftype in ("sent", "drafts", "trash", "spam"):
            return False

        sender = (idx.from_addr or "").lower()
        identities = {account.email.lower()} if account.email else set()

        if account.mail_server_id.user and "@" in account.mail_server_id.user:
            identities.add(account.mail_server_id.user.lower())
        if (
            account.mail_send_server_id.smtp_user
            and "@" in account.mail_send_server_id.smtp_user
        ):
            identities.add(account.mail_send_server_id.smtp_user.lower())

        if sender in identities:
            return False

        return True

    # ------------------------------------------------------------------
    # Queue scanning / selection
    # ------------------------------------------------------------------

    def scan_candidate_index_ids(self, batch: int) -> List[int]:
        aliases = self._get_aliases()
        condition, params = self._alias_condition(aliases)

        self.env.cr.execute(
            f"""
            SELECT idx.id
            FROM maildesk_message_index idx
            WHERE idx.deleted_on_server = FALSE
              AND idx.ingest_allowed = TRUE
              AND {condition}
              AND NOT EXISTS (
                  SELECT 1 FROM maildesk_ingest_queue q
                  WHERE q.index_id = idx.id
                    AND q.state IN ('done', 'pending', 'in_progress')
              )
            ORDER BY idx.date DESC, idx.id DESC
            LIMIT %s
            """,
            params + (int(batch),),
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def fetch_pending_queue_ids(self, batch: int, max_attempts: int, now):
        self.env.cr.execute(
            """
            SELECT id FROM maildesk_ingest_queue
            WHERE state IN ('pending', 'failed')
              AND retry_count < %s
              AND (next_try_at IS NULL OR next_try_at <= %s)
            ORDER BY priority ASC, id ASC
            FOR UPDATE SKIP LOCKED
            LIMIT %s
            """,
            (int(max_attempts), now, int(batch)),
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def mark_queue_in_progress(self, queue_id: int, now) -> bool:
        self.env.cr.execute(
            """
            UPDATE maildesk_ingest_queue
            SET state = 'in_progress',
                started_at = %s,
                error_message = NULL,
                write_date = NOW()
            WHERE id = %s AND state IN ('pending', 'failed')
            """,
            (now, int(queue_id)),
        )
        return self.env.cr.rowcount > 0

    def get_queue_context(self, queue_id: int):
        rec = self._queue().browse(int(queue_id))
        if not rec.exists() or not rec.index_id:
            return None
        idx = rec.index_id
        return QueueContext(
            queue_id=rec.id,
            state=rec.state,
            retry_count=rec.retry_count or 0,
            processed_res_id=rec.processed_res_id,
            index_id=idx.id,
            account_id=idx.account_id.id,
            provider=idx.provider,
            folder=idx.folder,
            uid=idx.uid,
            message_id=idx.message_id,
        )

    def list_stuck_in_progress(self, cutoff):
        recs = self._queue().search(
            [
                ("state", "=", "in_progress"),
                ("started_at", "!=", False),
                ("started_at", "<", cutoff),
            ]
        )
        return [
            StuckQueueInfo(queue_id=r.id, retry_count=r.retry_count or 0) for r in recs
        ]

    # ------------------------------------------------------------------
    # Processing helpers
    # ------------------------------------------------------------------

    def find_mail_message_by_message_id(self, message_id: str):
        if not message_id:
            return None
        rec = (
            self.env["mail.message"]
            .sudo()
            .search([("message_id", "=", message_id)], limit=1)
        )
        if not rec:
            return None
        return MailMessageInfo(model=rec.model, res_id=rec.res_id)

    def queue_store_raw_body(self, queue_id: int, raw_body: bytes) -> None:
        self._queue().browse(int(queue_id)).write({"raw_body": raw_body})

    def queue_mark_done(
        self,
        queue_id: int,
        processed_model: Optional[str],
        processed_res_id: Optional[int],
    ) -> None:
        # P0-1: Enforce state transition - only from in_progress
        self.env.cr.execute(
            """
            UPDATE maildesk_ingest_queue
            SET state = 'done',
                processed_at = %s,
                processed_model = %s,
                processed_res_id = %s,
                raw_body = NULL,
                error_message = NULL,
                started_at = NULL,
                write_date = NOW()
            WHERE id = %s AND state = 'in_progress'
            """,
            (fields.Datetime.now(), processed_model, processed_res_id, int(queue_id)),
        )
        if self.env.cr.rowcount == 0:
            _logger.error(
                "Failed to mark queue %s as done - not in in_progress state",
                queue_id,
            )

    def queue_mark_skipped(
        self,
        queue_id: int,
        error_message: str,
        processed_model: Optional[str] = None,
        processed_res_id: Optional[int] = None,
    ) -> None:
        # P0-1: Enforce state transition - only from in_progress
        # P0-5: Clear raw_body to prevent DB bloat
        self.env.cr.execute(
            """
            UPDATE maildesk_ingest_queue
            SET state = 'skipped',
                error_message = %s,
                processed_model = %s,
                processed_res_id = %s,
                processed_at = %s,
                raw_body = NULL,
                started_at = NULL,
                write_date = NOW()
            WHERE id = %s AND state = 'in_progress'
            """,
            (
                error_message[:1000] if error_message else None,
                processed_model,
                processed_res_id,
                fields.Datetime.now(),
                int(queue_id),
            ),
        )
        if self.env.cr.rowcount == 0:
            _logger.error(
                "Failed to mark queue %s as skipped - not in in_progress state",
                queue_id,
            )

    def queue_mark_failed(
        self,
        queue_id: int,
        retry_count: int,
        next_try_at,
        error_message: str,
    ) -> None:
        # P0-1: Enforce state transition - only from in_progress
        # P0-5: Clear raw_body to prevent DB bloat
        self.env.cr.execute(
            """
            UPDATE maildesk_ingest_queue
            SET state = 'failed',
                retry_count = %s,
                next_try_at = %s,
                error_message = %s,
                raw_body = NULL,
                started_at = NULL,
                write_date = NOW()
            WHERE id = %s AND state = 'in_progress'
            """,
            (
                int(retry_count),
                next_try_at,
                error_message[:1000] if error_message else None,
                int(queue_id),
            ),
        )
        if self.env.cr.rowcount == 0:
            _logger.error(
                "Failed to mark queue %s as failed - not in in_progress state",
                queue_id,
            )

    def requeue_failed_or_skipped(self, queue_id: int) -> bool:
        """
        P0-3: Reset a failed or skipped queue item back to pending state.
        Returns True if requeued, False if not in failed/skipped state.
        """
        self.env.cr.execute(
            """
            UPDATE maildesk_ingest_queue
            SET state = 'pending',
                retry_count = 0,
                next_try_at = NULL,
                error_message = NULL,
                raw_body = NULL,
                started_at = NULL,
                processed_at = NULL,
                write_date = NOW()
            WHERE id = %s AND state IN ('failed', 'skipped')
            """,
            (int(queue_id),),
        )
        return self.env.cr.rowcount > 0

    def mark_index_deleted(self, index_id: int) -> None:
        self._index().browse(int(index_id)).write({"deleted_on_server": True})

    def message_process(self, account_id: int, raw_body: bytes):
        account = self.env["mailbox.account"].sudo().browse(int(account_id))
        server = account.mail_server_id if account else False
        model = server.object_id.model if server and server.object_id else False
        return (
            self.env["mail.thread"]
            .sudo()
            .message_process(
                model,
                message=raw_body,
                save_original=server.original if server else False,
                strip_attachments=(not server.attach) if server else False,
            )
        )

    # ------------------------------------------------------------------
    # Provider raw fetch
    # ------------------------------------------------------------------

    def fetch_raw_body(self, ctx: QueueContext):
        account = self.env["mailbox.account"].sudo().browse(int(ctx.account_id))
        if not account:
            return None

        provider = (ctx.provider or "imap").lower()
        if provider == "gmail":
            return self._fetch_gmail_raw(account, ctx.uid)
        if provider == "outlook":
            return self._fetch_outlook_raw(account, ctx.uid)
        return self._fetch_imap_raw(account, ctx.folder, ctx.uid)

    def _fetch_imap_raw(self, account, folder_name: str, uid: str):
        client = build_authenticated_imap_client(self.env, account)
        try:
            client.select_folder(folder_name or "INBOX", readonly=True)
            uid_key = int(uid) if str(uid).isdigit() else uid
            data = client.fetch([uid_key], ["RFC822"]) or {}
            blob = None
            if uid_key in data:
                blob = data[uid_key].get(b"RFC822") or data[uid_key].get("RFC822")
            return blob
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _fetch_gmail_raw(self, account, uid: str):
        try:
            service = gmail_build_service(account)
            resp = (
                service.users()
                .messages()
                .get(userId="me", id=str(uid), format="raw")
                .execute()
            )
            raw_b64 = resp.get("raw") or ""
            if not raw_b64:
                return None
            return base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if status == 404:
                return None
            _logger.warning("Gmail raw fetch failed uid=%s: %s", uid, e)
            raise

    def _fetch_outlook_raw(self, account, uid: str):
        sess, base_url = get_outlook_client(self.env, account)
        if not sess or not base_url:
            raise Exception("Outlook client not available")

        url = f"{base_url}/me/messages/{uid}/$value"
        resp = sess.get(url)

        if resp.status_code == 200:
            return resp.content
        if resp.status_code == 404:
            return None

        _logger.warning(
            "Outlook raw fetch failed uid=%s status=%s", uid, resp.status_code
        )
        raise Exception(f"Outlook raw fetch failed: {resp.status_code}")
