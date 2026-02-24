# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Res Config Settings.

Defines Odoo ORM models and server-side APIs for Res Config Settings.
Layer: odoo models.
"""

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # PHASE 4: Cache TTL Configuration
    maildesk_cache_retention_days = fields.Integer(
        string="Email Cache Retention (days)",
        config_parameter="maildesk.cache_retention_days",
        default=30,
        help="How long to keep cached email bodies and attachments (30, 190, 365 days or custom)",
    )

    # Sync Batch Configuration
    maildesk_sync_batch_size = fields.Integer(
        string="Sync Batch Size",
        config_parameter="maildesk.sync_batch_size",
        default=100,
        help="Maximum number of messages to sync per batch operation",
    )

    maildesk_ingest_batch_size = fields.Integer(
        string="Ingest Queue Batch Size",
        config_parameter="maildesk.ingest_batch_size",
        default=50,
        help="Maximum number of messages to process from ingest queue per cron run",
    )

    maildesk_list_page_limit = fields.Integer(
        string="Messages Per Page",
        default=30,
        config_parameter="maildesk.list_page_limit",
        help="Number of messages to load per page in the message list view",
    )

    maildesk_backfill_bootstrap_max = fields.Integer(
        string="Bootstrap: Max Messages",
        default=1500,
        config_parameter="maildesk.backfill_bootstrap_max",
        help="Number of newest messages to fetch during fast bootstrap (default 1500)",
    )

    maildesk_backfill_batch_size = fields.Integer(
        string="Backfill: Batch Size",
        default=100,
        config_parameter="maildesk.backfill_batch_size",
        help="Messages per batch during progressive backfill (default 100)",
    )

    maildesk_backfill_job_budget_seconds = fields.Integer(
        string="Backfill: Job Budget (seconds)",
        default=25,
        config_parameter="maildesk.backfill_job_budget_seconds",
        help="Maximum seconds per backfill job execution (default 25s)",
    )

    maildesk_backfill_max_total_per_folder = fields.Integer(
        string="Backfill: Max Total Per Folder",
        default=20000,
        config_parameter="maildesk.backfill_max_total_per_folder",
        help="Maximum total messages to backfill per folder (default 20k, 0=unlimited)",
    )

    maildesk_backfill_mode = fields.Selection(
        [
            ("progressive", "Progressive (Bootstrap + Background)"),
            ("full", "Full Historical (Unbounded)"),
            ("from_now_on", "From Now On (No Backfill)"),
        ],
        string="Backfill Mode",
        default="progressive",
        config_parameter="maildesk.backfill_mode",
        help="Backfill strategy: progressive=fast bootstrap+background, full=all history, from_now_on=new only",
    )
