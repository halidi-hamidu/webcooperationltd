# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Ingest Queue Model - durable ingestion queue for mail.thread processing.

The model stores queue state only; orchestration is delegated to application
use-cases to keep ORM usage inside adapters.
"""

from odoo import api, fields, models

from ..application.use_cases.ingest_queue import (
    EnqueueIngestForMessageIndex,
    ProcessIngestQueueBatch,
    ProcessIngestQueueBatchParams,
    RecoverStuckIngestJobs,
    RecoverStuckIngestJobsParams,
    ScanSSOTForIngestion,
    ScanSSOTForIngestionParams,
)
from ..infrastructure.adapters.ingest_queue_adapter import IngestQueueAdapter


class MailDeskIngestQueue(models.Model):
    _name = "maildesk.ingest_queue"
    _description = "MailDesk: Message Ingestion Queue"
    _rec_name = "id"
    _order = "priority asc, id asc"

    index_id = fields.Many2one(
        "maildesk.message_index",
        required=True,
        index=True,
        ondelete="cascade",
    )

    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("failed", "Failed"),
            ("skipped", "Skipped"),
        ],
        default="pending",
        index=True,
        required=True,
    )

    retry_count = fields.Integer(default=0, index=True)
    next_try_at = fields.Datetime(index=True)
    error_message = fields.Text()

    raw_body = fields.Binary(attachment=False)

    processed_at = fields.Datetime(index=True)
    processed_model = fields.Char()
    processed_res_id = fields.Integer()

    priority = fields.Integer(default=10, index=True)

    started_at = fields.Datetime(index=True)

    _index_id_unique = models.Constraint(
        "UNIQUE (index_id)",
        "Each message can only be queued once",
    )

    @api.model
    def cron_scan_aliases(self, batch=500):
        adapter = IngestQueueAdapter(self.env)
        enqueue = EnqueueIngestForMessageIndex(adapter)
        return ScanSSOTForIngestion(adapter, enqueue).execute(
            ScanSSOTForIngestionParams(batch=batch)
        )

    @api.model
    def cron_import(self, batch=40, max_attempts=5, recover_timeout_minutes=30):
        adapter = IngestQueueAdapter(self.env)
        RecoverStuckIngestJobs(adapter).execute(
            RecoverStuckIngestJobsParams(timeout_minutes=recover_timeout_minutes)
        )
        return ProcessIngestQueueBatch(adapter).execute(
            ProcessIngestQueueBatchParams(batch=batch, max_attempts=max_attempts)
        )

    @api.model
    def cron_recover_stuck(self, timeout_minutes=30):
        adapter = IngestQueueAdapter(self.env)
        return RecoverStuckIngestJobs(adapter).execute(
            RecoverStuckIngestJobsParams(timeout_minutes=timeout_minutes)
        )

    def action_requeue(self):
        """Admin action: Requeue failed or skipped items"""
        adapter = IngestQueueAdapter(self.env)
        count = 0
        for record in self:
            if adapter.requeue_failed_or_skipped(record.id):
                count += 1

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": f"{count} queue item(s) reset to pending",
                "type": "success",
                "sticky": False,
            },
        }

    def action_clear_raw_body(self):
        """Admin action: Clear raw_body to free space"""
        self.write({"raw_body": False})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": f"Raw body cleared for {len(self)} item(s)",
                "type": "success",
                "sticky": False,
            },
        }
