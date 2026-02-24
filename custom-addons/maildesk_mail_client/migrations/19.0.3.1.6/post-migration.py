# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk v19.0.3.1.5 post-migration cleanup.

Purpose
-------
Versions prior to 19.0.3.1.5 could enqueue ingest jobs during bootstrap/backfill.
Those jobs may reach Odoo's incoming mail gateway (`mail.thread.message_process`).

Since 19.0.3.1.5, backfill/bootstrap is SSOT-only and ingestion is hard-gated by
`maildesk_message_index.ingest_allowed`.

This post-migration safely neutralizes any legacy queue rows that:
- are still actionable (pending/failed/in_progress), AND
- point to SSOT rows where ingest_allowed = FALSE.

The cleanup is idempotent and does not affect queue rows created by live
incremental sync (which sets ingest_allowed=TRUE).
"""

from __future__ import annotations

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_MIGRATION_FLAG = "maildesk_mail_client.migration_19_0_3_1_5_ingest_cleanup_done"


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


def _cleanup_legacy_ingest_queue(cr) -> int:
    if not _table_exists(cr, "maildesk_ingest_queue"):
        return 0
    if not _table_exists(cr, "maildesk_message_index"):
        return 0
    if not _column_exists(cr, "maildesk_message_index", "ingest_allowed"):
        # Field not present -> nothing we can safely gate by.
        return 0

    # "Safely skip": mark as skipped so they are never fetched by cron_import
    # (which selects only pending/failed), and never recovered from in_progress.
    cr.execute(
        """
        UPDATE maildesk_ingest_queue q
           SET state = 'skipped',
               error_message = 'Skipped by 19.0.3.1.5 migration: ingest_allowed=FALSE',
               next_try_at = NULL,
               raw_body = NULL,
               started_at = NULL,
               processed_at = NOW(),
               write_date = NOW()
          FROM maildesk_message_index idx
         WHERE q.index_id = idx.id
           AND q.state IN ('pending', 'failed', 'in_progress')
           AND (idx.ingest_allowed IS NULL OR idx.ingest_allowed = FALSE)
        """,
    )
    return int(cr.rowcount or 0)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    icp = env["ir.config_parameter"].sudo()

    if icp.get_param(_MIGRATION_FLAG) == "1":
        _logger.info("maildesk_mail_client: 19.0.3.1.5 ingest cleanup already applied")
        return

    count = _cleanup_legacy_ingest_queue(cr)
    icp.set_param(_MIGRATION_FLAG, "1")
    _logger.info("maildesk_mail_client: 19.0.3.1.5 ingest cleanup skipped=%s", count)
