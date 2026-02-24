# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Mailbox Account.

Defines Odoo ORM models and server-side APIs for Mailbox Account.
Layer: odoo models.
"""

import logging

from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, tools
from odoo.exceptions import AccessError, ValidationError

from ..application.services.imap_client_service import build_authenticated_imap_client
from ..application.use_cases import SyncImapFolderIncremental
from ..application.use_cases.sync_gmail_incremental import SyncGmailIncremental
from ..application.use_cases.sync_outlook_delta import SyncOutlookDelta
from ..infrastructure.adapters.bus_notification_adapter import BusNotificationAdapter
from ..infrastructure.providers.gmail.sync import GmailSyncProvider
from ..infrastructure.providers.imap.sync import ImapSyncProvider

_logger = logging.getLogger(__name__)


class MailboxAccount(models.Model):
    _name = "mailbox.account"
    _description = "Mailbox Account"
    _rec_name = "name"
    _order = "sequence, name"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    name = fields.Char(
        string="Account Name",
        required=True,
        translate=True,
        help="A friendly name for this account to identify it in Odoo (e.g. 'Support', 'Sales', 'John Doe').",
    )
    sender_name = fields.Char(
        help="The name displayed to recipients when you send an email (e.g. 'John Smith'). If empty, only the email address is shown.",
    )
    email = fields.Char(
        string="Email Address",
        required=True,
        index=True,
        help="The full email address used for login and sending mail (e.g. user@example.com).",
    )
    password = fields.Char(
        string="Share Password",
        help="Optional shared password for this mailbox. If set, users must enter this password to connect to the shared mailbox.",
    )
    block_tracking_urls = fields.Boolean(
        "Block Tracking URLs",
        help="If enabled, MailDesk attempts to strip known tracking pixels and links from incoming emails to protect privacy.",
    )

    mail_server_id = fields.Many2one(
        "fetchmail.server",
        string="Incoming Mail Server",
        copy=False,
        help="Configuration for receiving emails (IMAP).",
    )
    mail_send_server_id = fields.Many2one(
        "ir.mail_server",
        string="Outgoing SMTP Server",
        copy=False,
        help="Configuration for sending emails (SMTP).",
    )
    last_smtp_check = fields.Datetime(string="Last SMTP Capability Check")
    outlook_delta_link = fields.Char()

    max_email_size = fields.Float(
        string="Max Email Size (MB)",
        related="mail_send_server_id.max_email_size",
        readonly=False,
    )

    append_sent_to_imap = fields.Boolean(
        string="Append Sent to IMAP",
        default=True,
        help="If enabled, MailDesk will manually append sent copies to the IMAP Sent folder. "
        "Disable this if your SMTP server automatically saves sent messages (e.g. Gmail/Outlook).",
    )

    imap_caps = fields.Json(string="IMAP caps cache", default=lambda _=None: {})
    gmail_last_history_id = fields.Char(
        index=True, help="Gmail History API anchor (startHistoryId)"
    )
    gmail_last_sync_at = fields.Datetime(index=True)
    gmail_last_error = fields.Text()
    backoff_until = fields.Datetime(index=True)
    maildesk_sync_requested_at = fields.Datetime(
        index=True,
        help="Set by UI polling to request async sync; cleared by cron workers after pickup.",
    )
    outlook_delta_tokens = fields.Json(default=lambda _=None: {})

    signature = fields.Html(
        sanitize=False,
        help="HTML signature appended to every email sent from this account.",
    )
    folder_ids = fields.One2many("mailbox.folder", "account_id", string="Folders")

    owner_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        help="The primary owner of this account (usually the creator).",
    )
    is_shared = fields.Boolean(
        string="Shared Mailbox",
        default=False,
        help="Check this if this email account is shared among multiple users (e.g. support@). Allowed users can connect to it.",
    )
    access_user_ids = fields.Many2many(
        "res.users",
        "mailbox_account_user_rel",
        "account_id",
        "user_id",
        string="Users with Access",
        help="Select which Odoo users are allowed to see and use this mailbox account.",
    )
    attach_mail_server_id = fields.Boolean(
        related="mail_server_id.attach",
        string="Keep Attachments",
        help="If enabled, attachments will be downloaded and stored in Odoo. "
        "If disabled, attachments will remain on the mail server and will be fetched "
        "on demand when the email is viewed.",
        default=True,
        readonly=False,
    )
    show_recommendation = fields.Boolean(
        string="Show Email Hosting Recommendation",
        default=True,
        help="Whether to show the Metzler IT email hosting recommendation block.",
    )

    outlook_graph_refresh_token = fields.Char(
        groups="base.group_system",
        copy=False,
    )
    outlook_graph_access_token = fields.Char(
        groups="base.group_system",
        copy=False,
    )
    outlook_graph_access_token_expiration = fields.Integer(
        groups="base.group_system",
        copy=False,
    )
    outlook_graph_auth_state = fields.Selection(
        [
            ("ok", "OK"),
            ("reauth_required", "Reconnect Required"),
            ("auth_invalid", "Invalid OAuth Configuration"),
        ],
        default="ok",
        groups="base.group_system",
        copy=False,
        help="MailDesk Outlook Graph authentication state. "
        "If set to 'Invalid OAuth Configuration', cron sync is paused to prevent retry storms "
        "until the Client Secret is fixed and the mailbox is reconnected.",
    )
    outlook_graph_auth_error = fields.Text(
        groups="base.group_system",
        copy=False,
        help="Last Graph authentication error captured by MailDesk. Used for diagnostics.",
    )

    is_outlook = fields.Boolean(compute="_compute_provider_type")
    is_gmail = fields.Boolean(compute="_compute_provider_type")

    @api.depends("mail_server_id", "email", "imap_caps")
    def _compute_provider_type(self):
        for rec in self:
            rec.is_outlook = rec._is_outlook_check()
            rec.is_gmail = rec._is_gmail_check()

    @api.constrains("mail_server_id", "mail_send_server_id")
    def _check_unique_servers(self):
        """
        Enforces that incoming and outgoing servers are linked to only one
        mailbox account to avoid connection conflicts. Searches sibling records
        for reused server references and raises validation errors so each server
        configuration remains uniquely bound.
        """
        for rec in self:
            if rec.mail_server_id:
                others = self.search(
                    [
                        ("id", "!=", rec.id),
                        ("mail_server_id", "=", rec.mail_server_id.id),
                    ]
                )
                if others:
                    raise ValidationError(
                        self.env._(
                            "Incoming mail server %(server)s is already linked to another mailbox account.",
                            server=rec.mail_server_id.display_name,
                        )
                    )

            if rec.mail_send_server_id:
                others = self.search(
                    [
                        ("id", "!=", rec.id),
                        ("mail_send_server_id", "=", rec.mail_send_server_id.id),
                    ]
                )
                if others:
                    raise ValidationError(
                        self.env._(
                            "Outgoing mail server %(server)s is already linked to another mailbox account.",
                            server=rec.mail_send_server_id.display_name,
                        )
                    )

    def button_test_incoming(self):
        """
        Validates the configured incoming mail server by attempting login and
        then refreshes cached IMAP capabilities. Returns a client action
        notification indicating success so administrators receive immediate
        feedback.
        """
        if not self.mail_server_id:
            raise ValidationError(
                self.env._(
                    "No incoming mail server configured. Please configure it in the server settings."
                )
            )
        self.mail_server_id.button_confirm_login()
        self.refresh_imap_caps(force=True, update_kind=True)

        for acc in self:
            if not acc.folder_ids:
                try:
                    acc.sync_imap_folders()
                except Exception as e:
                    _logger.warning(
                        "Initial folder sync failed for account %s: %s", acc.name, e
                    )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": self.env._("Connection Test Successful!"),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def button_test_outgoing(self):
        """
        Confirms the outgoing SMTP server works by performing a connection test
        and refreshing IMAP capability metadata afterward. Presents a success
        notification to the user, mirroring the incoming test flow.
        """
        if not self.mail_send_server_id:
            raise ValidationError(
                self.env._(
                    "No outgoing SMTP server configured. Please configure it in the server settings."
                )
            )
        self.mail_send_server_id.test_smtp_connection()
        self.refresh_imap_caps(force=True, update_kind=True)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": self.env._("Connection Test Successful!"),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_setup_gmail(self):
        """
        Redirects to Gmail setup documentation.
        """
        return {
            "type": "ir.actions.act_url",
            "url": "https://mit-odoo.de/maildesk-gmail-docs",
            "target": "new",
        }

    def action_setup_outlook(self):
        """
        Redirects to Outlook setup documentation.
        """
        return {
            "type": "ir.actions.act_url",
            "url": "https://mit-odoo.de/maildesk-outlook-docs",
            "target": "new",
        }

    def action_setup_imap(self):
        """
        Redirects to IMAP setup documentation.
        """
        return {
            "type": "ir.actions.act_url",
            "url": "https://mit-odoo.de/maildesk-imap-docs",
            "target": "new",
        }

    def action_view_documentation(self):
        """
        Redirects to general documentation.
        """
        return {
            "type": "ir.actions.act_url",
            "url": "https://mit-odoo.de/maildesk/docs",
            "target": "new",
        }

    def action_auth_outlook_graph(self):
        """
        Triggers the dedicated Microsoft Graph OAuth flow.
        """
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return {
            "type": "ir.actions.act_url",
            "url": f"{base_url}/maildesk/outlook/authorize?account_id={self.id}",
            "target": "self",
        }

    def action_reset_mailbox_sync_state(self):
        """
        Reset synchronization state for this mailbox account (DB-only).

        This is the administrator-facing equivalent of the MailDesk v3.0.0
        post-migration reset, but scoped to the selected account(s).

        Guarantees:
        - No provider calls are executed (IMAP/Gmail/Graph are never contacted).
        - OAuth tokens and server configuration are preserved.
        - Existing cron jobs naturally re-bootstrap and resume sync.
        """
        if not self.env.user.has_group("maildesk_mail_client.group_mailbox_admin"):
            raise AccessError(self.env._("Only administrators can reset sync state."))

        accounts = self.sudo()
        account_ids = accounts.ids
        if not account_ids:
            return True

        accounts.write(
            {
                "gmail_last_history_id": False,
                "gmail_last_sync_at": False,
                "gmail_last_error": False,
                "outlook_delta_tokens": {},
                "outlook_delta_link": False,
                "backoff_until": False,
                "maildesk_sync_requested_at": False,
            }
        )

        Folder = self.env["mailbox.folder"].sudo()
        folders = Folder.search([("account_id", "in", account_ids)])
        if folders:
            folders.write(
                {
                    "sync_state": "backfill_pending",
                    "last_uid": 0,
                    "last_uidnext": 0,
                    "last_highest_modseq": "0",
                    "sync_modseq": "0",
                    "needs_sync": False,
                    "backfill_last_uid": 0,
                    "backfill_started_at": False,
                    "backfill_completed_at": False,
                    "backfill_fetched_count": 0,
                    "backfill_total_estimate": 0,
                    "gmail_label_id": False,
                    "gmail_backfill_page_token": False,
                    "outlook_backfill_next_link": False,
                    "last_sync_at": False,
                    "last_error": False,
                }
            )

        cr = self.env.cr

        # Clear optimistic UI overlays and any stuck leases; both are safe to rebuild.
        cr.execute(
            "DELETE FROM maildesk_email_state WHERE account_id IN %s",
            (tuple(account_ids),),
        )
        cr.execute(
            "DELETE FROM maildesk_account_lease WHERE account_id IN %s",
            (tuple(account_ids),),
        )

        # Hide SSOT rows so no stale data is shown while rebuild runs.
        # Keep local_pending entries (sent/drafts) to avoid losing user-visible work.
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

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Sync reset scheduled"),
                "message": self.env._(
                    "Synchronization state was reset. Emails will be temporarily unavailable until resynchronization completes automatically."
                ),
                "type": "warning",
                "sticky": False,
            },
        }

    @api.constrains("email")
    def _check_email_format(self):
        """
        Guards against saving accounts with malformed email addresses by
        verifying the presence of an '@' character. Raises a validation error
        immediately so records are not persisted with unusable sender data.
        """
        for record in self:
            if record.email and "@" not in record.email:
                raise ValidationError(self.env._("Invalid email address format."))

    def get_smtp_server(self):
        """
        Returns the outgoing server configured on the account. Ensures a single
        record context before exposing the related SMTP server record.
        """
        self.ensure_one()
        return self.mail_send_server_id

    def _is_gmail_check(self):
        """Returns True if the account is a Gmail account."""
        self.ensure_one()
        mail_server = self.mail_server_id.sudo()
        if mail_server.server_type == "gmail":
            return True
        # Smart detection via host/caps
        host = (mail_server.server or "").lower()
        email = (self.email or "").lower()
        domain = email.split("@")[1].lower() if "@" in email else ""
        caps = self.imap_caps.get("tokens", []) if self.imap_caps else []
        caps_set = {str(c).upper() for c in caps}
        return (
            "X-GM-EXT-1" in caps_set
            or "google" in host
            or domain in ("gmail.com", "googlemail.com")
        )

    def _is_outlook_check(self):
        """Returns True if the account is an Outlook account."""
        self.ensure_one()
        mail_server = self.mail_server_id.sudo()
        if mail_server.server_type == "outlook":
            return True
        # Smart detection via host/caps
        host = (mail_server.server or "").lower()
        email = (self.email or "").lower()
        domain = email.split("@")[1].lower() if "@" in email else ""
        caps = self.imap_caps.get("tokens", []) if self.imap_caps else []
        caps_set = {str(c).upper() for c in caps}
        return (
            any(
                x in host
                for x in ("outlook", "office365", "hotmail", "live", "prod.outlook.com")
            )
            or domain.endswith((".onmicrosoft.com", ".office365.com", ".outlook.com"))
            or "MICROSOFT" in caps_set
        )

    def get_imap_server(self):
        """
        Provides the incoming server linked to the mailbox account after
        enforcing singleton semantics. Used by caller code that needs direct
        access to the fetchmail server configuration.
        """
        self.ensure_one()
        return self.mail_server_id

    def sync_imap_folders(self):
        """
        Triggers folder synchronization for each account by delegating to the
        folder model helper. Iterates over the current recordset so each account
        refreshes its IMAP folder mapping.
        """
        Folder = self.env["mailbox.folder"]
        for account in self:
            if not account.mail_server_id:
                _logger.warning(
                    "Skipping IMAP folder sync for account %s: no incoming server configured.",
                    account.id,
                )
                continue
            Folder.sync_folders_for_account(account)

    def _caps_normalize(self, caps):
        """
        Standardizes IMAP capability tokens into a sorted uppercase list for
        consistent comparison. Handles bytes values from IMAP responses and
        deduplicates tokens so downstream capability checks are stable.
        """
        if not caps:
            return []
        return sorted(
            {(c.decode() if isinstance(c, bytes) else c).upper() for c in caps}
        )

    def refresh_imap_caps(self, force=False, update_kind=True, ttl_hours=24):
        """
        Refreshes cached IMAP capabilities when stale or on demand and optionally
        updates the inferred server kind. Contacts the IMAP server, captures the
        capability tokens, stores them alongside a timestamp, and triggers kind
        recalculation when appropriate while tolerating connection or write
        errors silently.
        """
        for acc in self:
            data = {}
            try:
                data = acc.imap_caps or {}
            except Exception:
                data = {}

            checked = data.get("checked")
            fresh = False
            if checked:
                try:
                    fresh = fields.Datetime.from_string(
                        checked
                    ) > fields.Datetime.now() - relativedelta(hours=ttl_hours)
                except Exception:
                    fresh = False

            if fresh and not force:
                continue

            tokens = []
            try:
                cli = acc._get_imap_client()
                try:
                    caps_raw = cli.capabilities()
                except Exception:
                    caps_raw = []

                try:
                    tokens = acc._caps_normalize(caps_raw)
                except Exception:
                    tokens = []

                try:
                    cli.logout()
                except Exception as e:
                    _logger.debug("ignored error: %s", e)

            except Exception:
                tokens = []

            try:
                acc.sudo().write(
                    {
                        "imap_caps": {
                            "checked": fields.Datetime.now().isoformat(),
                            "tokens": tokens,
                        }
                    }
                )
            except Exception:
                continue

            except Exception:
                continue

    def get_imap_caps(self, ttl_hours=24):
        """
        Returns cached IMAP capability tokens, refreshing them when older than
        the provided TTL. Guarantees a singleton context, pulls fresh capabilities
        if necessary, and normalizes the tokens into a comparable set for
        capability checks elsewhere.
        """
        self.ensure_one()
        data = self.imap_caps or {}
        checked = data.get("checked")
        fresh = False
        if checked:
            try:
                fresh = fields.Datetime.from_string(
                    checked
                ) > fields.Datetime.now() - relativedelta(hours=ttl_hours)
            except Exception as e:
                _logger.debug("ignored error: %s", e)
        if not fresh:
            self.refresh_imap_caps(force=True, update_kind=False)
            data = self.imap_caps or {}
        return set(self._caps_normalize(data.get("tokens")))

    def _get_imap_client(self):
        """
        Delegates IMAP client creation to the infrastructure factory.
        """
        return build_authenticated_imap_client(self.env, self)

    # =========================================================================
    # FRONTEND RPC ENTRY POINTS
    # These methods are called by the frontend and delegate to appropriate
    # services/models following Clean Architecture principles.
    # =========================================================================

    @api.model
    def get_account_list(self):
        """
        Return the list of mailbox accounts accessible by the current user.
        Used by frontend on initial load.

        Returns:
            list: List of account dicts with id, name, email, signature, etc.
        """
        accounts = self.search(
            [("access_user_ids", "in", [self.env.uid])], order="sequence, name"
        )
        return [
            {
                "id": acc.id,
                "name": acc.name,
                "email": acc.email,
                "sender_name": acc.sender_name or acc.name,
                "signature": acc.signature or "",
                "is_shared": acc.is_shared,
                "block_tracking_urls": acc.block_tracking_urls,
                "sequence": acc.sequence,
            }
            for acc in accounts
        ]

    @api.model
    def get_folder_tree(self, account_id):
        """
        Return the folder tree for a specific account.
        Delegates to mailbox.folder.get_folder_tree for implementation.

        Args:
            account_id: ID of the mailbox account

        Returns:
            list: Nested folder structure with id, name, folder_type, children
        """
        return self.env["mailbox.folder"].get_folder_tree(account_id)

    @api.model
    def get_message_with_attachments(self, params):
        """
        Fetch full message details including body and attachments.
        Delegates to mailbox.sync for implementation.

        Args:
            params: Dict with uid, account_id, folder_id, is_internal_draft

        Returns:
            dict: Full message DTO with body_original, attachments, etc.
        """
        return self.env["mailbox.sync"].get_message_with_attachments(params)

    @api.model
    def poll_mail_accounts(self):
        """
        UI polling entrypoint (non-blocking).

        This method MUST NOT execute sync work (IMAP/Gmail/Outlook) and MUST NOT
        acquire leases. It only enqueues an async sync request which is later
        consumed by cron workers.

        This is the ONLY entry point for polling. NO watchers, NO IDLE.
        Backend decides which accounts need sync based on their state.

        Returns:
            dict: Summary of sync results with changes flag and stats
        """
        accounts = self.search(
            [("access_user_ids", "in", [self.env.uid])], order="sequence, name"
        )
        if not accounts:
            return {"changes": False, "queued_accounts": 0}

        requested_at = fields.Datetime.now()
        # Enqueue is idempotent per-account: repeated polls keep one pending request.
        #
        # Note: this must run on the current cursor/transaction. Using a separate cursor
        # breaks TransactionCase fixtures (rows are uncommitted/locked) and can cause the
        # poll to "skip" freshly created accounts due to SKIP LOCKED.
        self.env.cr.execute(
            """
            WITH candidates AS (
                SELECT id
                FROM mailbox_account
                WHERE id IN %s
                  AND maildesk_sync_requested_at IS NULL
                FOR NO KEY UPDATE SKIP LOCKED
            )
            UPDATE mailbox_account
            SET maildesk_sync_requested_at = %s,
                write_date = now()
            WHERE id IN (SELECT id FROM candidates)
            RETURNING id
            """,
            (tuple(accounts.ids), requested_at),
        )
        queued_ids = [row[0] for row in self.env.cr.fetchall()]

        return {
            "changes": False,
            "queued_accounts": len(queued_ids),
            "requested_accounts": len(accounts),
        }

    @api.model
    def cron_gmail_history_sync(self, batch=5, lease_ttl=300):
        """
        Cron entrypoint for Gmail incremental sync (History API, Stage-3).
        """
        Lease = self.env["maildesk.account_lease"].sudo()
        Lease.reap_expired()

        now = fields.Datetime.now()
        candidates = self.search(
            [
                ("active", "=", True),
                "|",
                ("backoff_until", "=", False),
                ("backoff_until", "<=", now),
            ]
        )
        gmail_ids = [acc.id for acc in candidates if acc.is_gmail]
        if not gmail_ids:
            return {"ok": True, "processed": 0, "success": 0, "failed": 0}

        self.env.cr.execute(
            """
            SELECT id FROM mailbox_account
            WHERE id IN %s
            ORDER BY maildesk_sync_requested_at IS NULL,
                     maildesk_sync_requested_at ASC NULLS LAST,
                     id
            FOR NO KEY UPDATE SKIP LOCKED
            LIMIT %s
            """,
            (tuple(gmail_ids), int(batch)),
        )
        locked_ids = [row[0] for row in self.env.cr.fetchall()]
        if not locked_ids:
            return {"ok": True, "processed": 0, "success": 0, "failed": 0}

        notifier = BusNotificationAdapter(self.env)
        sync = SyncGmailIncremental(
            self.env, notifier=notifier, lease_ttl_seconds=int(lease_ttl)
        )
        stats = {"ok": True, "processed": 0, "success": 0, "failed": 0}

        for acc_id in locked_ids:
            stats["processed"] += 1
            try:
                res = sync.execute(acc_id)
                if res.get("ok"):
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
            except Exception:
                stats["failed"] += 1
                _logger.exception("Gmail sync failed for account %s", acc_id)
            finally:
                self.browse(acc_id).sudo().write({"maildesk_sync_requested_at": False})

        return stats

    @api.model
    def cron_outlook_delta_sync(self, batch=5, lease_ttl=300):
        """
        Cron entrypoint for Outlook Graph delta sync (Stage-4).
        """
        Lease = self.env["maildesk.account_lease"].sudo()
        Lease.reap_expired()

        now = fields.Datetime.now()
        candidates = self.search(
            [
                ("active", "=", True),
                "|",
                ("backoff_until", "=", False),
                ("backoff_until", "<=", now),
            ]
        )
        outlook_ids = [
            acc.id
            for acc in candidates
            if acc.is_outlook and (acc.outlook_graph_auth_state or "ok") == "ok"
        ]
        if not outlook_ids:
            return {"ok": True, "processed": 0, "success": 0, "failed": 0}

        self.env.cr.execute(
            """
            SELECT id FROM mailbox_account
            WHERE id IN %s
            ORDER BY maildesk_sync_requested_at IS NULL,
                     maildesk_sync_requested_at ASC NULLS LAST,
                     id
            FOR NO KEY UPDATE SKIP LOCKED
            LIMIT %s
            """,
            (tuple(outlook_ids), int(batch)),
        )
        locked_ids = [row[0] for row in self.env.cr.fetchall()]
        if not locked_ids:
            return {"ok": True, "processed": 0, "success": 0, "failed": 0}

        notifier = BusNotificationAdapter(self.env)
        sync = SyncOutlookDelta(
            self.env, notifier=notifier, lease_ttl_seconds=int(lease_ttl)
        )
        stats = {"ok": True, "processed": 0, "success": 0, "failed": 0}

        for acc_id in locked_ids:
            stats["processed"] += 1
            try:
                res = sync.execute(acc_id)
                if res.get("ok"):
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
            except Exception:
                stats["failed"] += 1
                _logger.exception("Outlook sync failed for account %s", acc_id)
            finally:
                self.browse(acc_id).sudo().write({"maildesk_sync_requested_at": False})

        return stats

    @api.model
    def cron_imap_inbox_incremental_sync(self, batch=5, lease_ttl=300):
        """
        Cron entrypoint for IMAP INBOX incremental sync (Stage-4).
        """
        Lease = self.env["maildesk.account_lease"].sudo()
        Lease.reap_expired()

        now = fields.Datetime.now()
        candidates = self.search(
            [
                ("active", "=", True),
                "|",
                ("backoff_until", "=", False),
                ("backoff_until", "<=", now),
            ]
        )
        imap_ids = [
            acc.id for acc in candidates if not acc.is_gmail and not acc.is_outlook
        ]
        if not imap_ids:
            return {"ok": True, "processed": 0, "success": 0, "failed": 0}

        self.env.cr.execute(
            """
            SELECT id FROM mailbox_account
            WHERE id IN %s
            ORDER BY maildesk_sync_requested_at IS NULL,
                     maildesk_sync_requested_at ASC NULLS LAST,
                     id
            FOR NO KEY UPDATE SKIP LOCKED
            LIMIT %s
            """,
            (tuple(imap_ids), int(batch)),
        )
        locked_ids = [row[0] for row in self.env.cr.fetchall()]
        if not locked_ids:
            return {"ok": True, "processed": 0, "success": 0, "failed": 0}

        notifier = BusNotificationAdapter(self.env)

        sync = SyncImapFolderIncremental(
            self.env, notifier=notifier, lease_ttl_seconds=int(lease_ttl)
        )
        stats = {"ok": True, "processed": 0, "success": 0, "failed": 0}

        for acc_id in locked_ids:
            stats["processed"] += 1
            try:
                res = sync.execute(acc_id)
                if res.get("ok"):
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
            except Exception:
                stats["failed"] += 1
                _logger.exception("IMAP sync failed for account %s", acc_id)
            finally:
                self.browse(acc_id).sudo().write({"maildesk_sync_requested_at": False})

        return stats

    @api.model
    def get_migration_status(self):
        """
        Operational snapshot for SSOT runtime status.
        """
        accounts = self.search([("active", "=", True)])

        details = []
        for acc in accounts:
            if acc.is_gmail:
                provider = "gmail"
            elif acc.is_outlook:
                provider = "outlook"
            else:
                provider = "imap"
            details.append(
                {
                    "id": acc.id,
                    "name": acc.name,
                    "provider": provider,
                    "ssot": provider in ("gmail", "imap"),
                }
            )

        return {
            "ssot_read": True,
            "gmail_sync": True,
            "imap_sync": True,
            "accounts": details,
        }

    def _poll_single_account(self, account):
        """
        Execute incremental sync for a single account.
        Provider-specific logic is handled by the sync orchestrator.

        Args:
            account: mailbox.account record

        Returns:
            dict: Sync result with changes flag
        """
        # Import here to avoid circular dependency
        try:
            if account.is_gmail:
                # Gmail uses History API for incremental sync
                provider = GmailSyncProvider(self.env, account)
                return provider.poll_incremental()
            elif account.is_outlook:
                notifier = BusNotificationAdapter(self.env)
                sync = SyncOutlookDelta(self.env, notifier=notifier)
                return sync.execute(account.id)
            else:
                # IMAP uses UID-based incremental sync
                provider = ImapSyncProvider(self.env, account)
                return provider.poll_incremental()
        except ImportError as e:
            _logger.debug("Sync provider not available: %s", e)
            return {"changes": False}
        except Exception as e:
            _logger.warning("Sync error for account %s: %s", account.id, e)
            return {"changes": False}

    @api.model_create_multi
    def create(self, vals_list):
        """
        Creates mailbox accounts and immediately refreshes IMAP capabilities for
        those linked to an incoming server. Ensures the provider kind and
        capability cache are populated as soon as the record is created.
        """
        records = super().create(vals_list)
        if tools.config.get("test_enable"):
            return records

        records_with_server = records.filtered(
            lambda r: r.mail_server_id and r.mail_server_id.server_type == "imap"
        )
        for record in records_with_server:
            record.refresh_imap_caps(force=True, update_kind=False)
        return records
