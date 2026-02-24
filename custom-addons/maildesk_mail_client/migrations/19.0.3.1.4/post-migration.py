# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk v3.0.0 post-migration reset.

Purpose
-------
MailDesk v3 must not trust any v2 synchronization state. This post-migration
hook resets all provider cursors and folder state machines to a canonical
"re-bootstrap needed" state, so the existing MailDesk v3 crons naturally run:

    backfill_pending (bootstrap) → incremental (incremental sync) → progressive backfill

Scope / invariants
------------------
- No external network calls are performed here.
- OAuth tokens / credentials are preserved.
- The module's existing bootstrap/backfill/incremental flows remain the only
  mechanisms that rebuild SSOT.

Layer: migrations.
"""

from __future__ import annotations

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_MIGRATION_FLAG = "maildesk_mail_client.migration_19_0_3_0_0_post_done"

# Hard-delete can be expensive on very large SSOT tables. Above this threshold
# we switch to a "soft reset" (hide entries + clear dependent cache/queue rows).
_SSOT_HARD_DELETE_MAX_ROWS = 250_000
_SSOT_DELETE_BATCH = 10_000


def _table_exists(cr, table_name: str) -> bool:
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = %s
        """,
        (table_name,),
    )
    return bool(cr.fetchone())


def _column_exists(cr, table_name: str, column_name: str) -> bool:
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = %s
           AND column_name = %s
        """,
        (table_name, column_name),
    )
    return bool(cr.fetchone())


def _maildesk_account_ids(cr) -> list[int]:
    """
    Return mailbox.account ids managed by MailDesk.

    MailDesk accounts are represented by `mailbox.account` records; the module
    must be resilient if some accounts are partially configured.
    """
    if not _table_exists(cr, "mailbox_account"):
        return []
    cr.execute("SELECT id FROM mailbox_account ORDER BY id")
    return [int(row[0]) for row in cr.fetchall()]


def _reset_accounts(cr, account_ids: list[int]) -> None:
    if not account_ids or not _table_exists(cr, "mailbox_account"):
        return

    set_parts = []
    if _column_exists(cr, "mailbox_account", "gmail_last_history_id"):
        set_parts.append("gmail_last_history_id = NULL")
    if _column_exists(cr, "mailbox_account", "gmail_last_sync_at"):
        set_parts.append("gmail_last_sync_at = NULL")
    if _column_exists(cr, "mailbox_account", "gmail_last_error"):
        set_parts.append("gmail_last_error = NULL")
    if _column_exists(cr, "mailbox_account", "outlook_delta_link"):
        set_parts.append("outlook_delta_link = NULL")
    if _column_exists(cr, "mailbox_account", "outlook_delta_tokens"):
        set_parts.append("outlook_delta_tokens = '{}'::jsonb")
    if _column_exists(cr, "mailbox_account", "backoff_until"):
        set_parts.append("backoff_until = NULL")
    if _column_exists(cr, "mailbox_account", "maildesk_sync_requested_at"):
        set_parts.append("maildesk_sync_requested_at = NULL")

    if not set_parts:
        return

    cr.execute(
        f"""
        UPDATE mailbox_account
           SET {", ".join(set_parts)},
               write_date = NOW()
         WHERE id IN %s
        """,
        (tuple(account_ids),),
    )
    _logger.info("maildesk_mail_client: reset accounts=%s", cr.rowcount)


def _reset_folders(cr, account_ids: list[int]) -> None:
    if not account_ids or not _table_exists(cr, "mailbox_folder"):
        return

    set_parts = [
        "sync_state = 'backfill_pending'",
        "last_uid = 0",
        "backfill_last_uid = 0",
        "backfill_started_at = NULL",
        "backfill_completed_at = NULL",
        "backfill_fetched_count = 0",
        "backfill_total_estimate = 0",
        "needs_sync = FALSE",
        "last_uidnext = 0",
        "last_highest_modseq = '0'",
        "sync_modseq = '0'",
        "last_sync_at = NULL",
        "last_error = NULL",
    ]

    if _column_exists(cr, "mailbox_folder", "gmail_backfill_page_token"):
        set_parts.append("gmail_backfill_page_token = NULL")
    if _column_exists(cr, "mailbox_folder", "gmail_label_id"):
        set_parts.append("gmail_label_id = NULL")
    if _column_exists(cr, "mailbox_folder", "outlook_backfill_next_link"):
        set_parts.append("outlook_backfill_next_link = NULL")

    # `outlook_graph_id` is a stable folder identity, not a cursor. It is
    # intentionally preserved to avoid ambiguous name-based folder resolution.
    # The incremental delta cursors are reset at account level.

    cr.execute(
        f"""
        UPDATE mailbox_folder
           SET {", ".join(set_parts)},
               write_date = NOW()
         WHERE account_id IN %s
        """,
        (tuple(account_ids),),
    )
    _logger.info("maildesk_mail_client: reset folders=%s", cr.rowcount)


def _reset_email_state(cr, account_ids: list[int]) -> None:
    if not account_ids or not _table_exists(cr, "maildesk_email_state"):
        return
    cr.execute(
        "DELETE FROM maildesk_email_state WHERE account_id IN %s",
        (tuple(account_ids),),
    )
    _logger.info("maildesk_mail_client: cleared email_state=%s", cr.rowcount)


def _reset_account_leases(cr, account_ids: list[int]) -> None:
    if not account_ids or not _table_exists(cr, "maildesk_account_lease"):
        return
    cr.execute(
        "DELETE FROM maildesk_account_lease WHERE account_id IN %s",
        (tuple(account_ids),),
    )
    _logger.info("maildesk_mail_client: cleared account_lease=%s", cr.rowcount)


def _hard_delete_ssot(cr, account_ids: list[int]) -> int:
    deleted_total = 0
    while True:
        cr.execute(
            """
            WITH ids AS (
                SELECT id
                  FROM maildesk_message_index
                 WHERE account_id IN %s
                   AND (local_pending IS NULL OR local_pending = FALSE)
                 ORDER BY id
                 LIMIT %s
            )
            DELETE FROM maildesk_message_index idx
             USING ids
             WHERE idx.id = ids.id
            """,
            (tuple(account_ids), int(_SSOT_DELETE_BATCH)),
        )
        if cr.rowcount <= 0:
            break
        deleted_total += int(cr.rowcount)
    return deleted_total


def _soft_reset_ssot(cr, account_ids: list[int]) -> dict:
    """
    Hide stale SSOT rows without deleting the full table content.

    This keeps the table size stable (avoids long-running deletes) while
    ensuring list views never show stale entries. Bootstrap/backfill upserts
    will re-activate rows by writing `deleted_on_server = FALSE` again.
    """
    stats = {
        "index_hidden": 0,
        "ui_cache_deleted": 0,
        "queue_deleted": 0,
        "tags_deleted": 0,
    }

    if not _table_exists(cr, "maildesk_message_index"):
        return stats

    cr.execute(
        """
        UPDATE maildesk_message_index
           SET deleted_on_server = TRUE,
               pending_move_to = NULL,
               pending_delete = FALSE,
               write_date = NOW()
         WHERE account_id IN %s
           AND (local_pending IS NULL OR local_pending = FALSE)
        """,
        (tuple(account_ids),),
    )
    stats["index_hidden"] = int(cr.rowcount)

    if _table_exists(cr, "maildesk_ui_cache"):
        cr.execute(
            """
            DELETE FROM maildesk_ui_cache c
             USING maildesk_message_index idx
             WHERE c.index_id = idx.id
               AND idx.account_id IN %s
               AND (idx.local_pending IS NULL OR idx.local_pending = FALSE)
            """,
            (tuple(account_ids),),
        )
        stats["ui_cache_deleted"] = int(cr.rowcount)

    if _table_exists(cr, "maildesk_ingest_queue"):
        cr.execute(
            """
            DELETE FROM maildesk_ingest_queue q
             USING maildesk_message_index idx
             WHERE q.index_id = idx.id
               AND idx.account_id IN %s
               AND (idx.local_pending IS NULL OR idx.local_pending = FALSE)
            """,
            (tuple(account_ids),),
        )
        stats["queue_deleted"] = int(cr.rowcount)

    if _table_exists(cr, "maildesk_index_tag_rel"):
        cr.execute(
            """
            DELETE FROM maildesk_index_tag_rel rel
             USING maildesk_message_index idx
             WHERE rel.index_id = idx.id
               AND idx.account_id IN %s
               AND (idx.local_pending IS NULL OR idx.local_pending = FALSE)
            """,
            (tuple(account_ids),),
        )
        stats["tags_deleted"] = int(cr.rowcount)

    return stats


def _reset_ssot(cr, account_ids: list[int]) -> None:
    if not account_ids or not _table_exists(cr, "maildesk_message_index"):
        return

    cr.execute(
        """
        SELECT COUNT(*)
          FROM maildesk_message_index
         WHERE account_id IN %s
           AND (local_pending IS NULL OR local_pending = FALSE)
        """,
        (tuple(account_ids),),
    )
    count = int((cr.fetchone() or [0])[0])

    if count <= 0:
        _logger.info("maildesk_mail_client: SSOT reset skipped (no rows)")
        return

    if count <= _SSOT_HARD_DELETE_MAX_ROWS:
        deleted = _hard_delete_ssot(cr, account_ids)
        _logger.info("maildesk_mail_client: SSOT hard-deleted=%s", deleted)
        return

    stats = _soft_reset_ssot(cr, account_ids)
    _logger.info(
        "maildesk_mail_client: SSOT soft-reset rows=%s ui_cache=%s queue=%s tags=%s",
        stats["index_hidden"],
        stats["ui_cache_deleted"],
        stats["queue_deleted"],
        stats["tags_deleted"],
    )


def maildesk_post_migrate_3_0_0(env) -> None:
    """
    Reset all MailDesk v2 sync state to v3 canonical reset.

    This function is intentionally DB-only: it does not call providers and
    does not execute bootstrap/backfill/incremental use cases.
    """
    icp = env["ir.config_parameter"].sudo()
    if icp.get_param(_MIGRATION_FLAG) == "1":
        _logger.info("maildesk_mail_client: v3.0.0 post-migration already applied")
        return

    cr = env.cr
    account_ids = _maildesk_account_ids(cr)
    _logger.info(
        "maildesk_mail_client: v3.0.0 post-migration accounts=%s", len(account_ids)
    )
    if not account_ids:
        icp.set_param(_MIGRATION_FLAG, "1")
        return

    _reset_accounts(cr, account_ids)
    _reset_folders(cr, account_ids)
    _reset_ssot(cr, account_ids)
    _reset_email_state(cr, account_ids)
    _reset_account_leases(cr, account_ids)

    icp.set_param(_MIGRATION_FLAG, "1")
    _logger.info("maildesk_mail_client: v3.0.0 post-migration done")


def migrate(cr, version):
    _logger.info(
        "maildesk_mail_client: v3.0.0 post-migration start (version %s)", version
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    maildesk_post_migrate_3_0_0(env)
