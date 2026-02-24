# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Mailbox Folder.

Defines Odoo ORM models and server-side APIs for Mailbox Folder.
Layer: odoo models.
"""

import logging

import psycopg2
from imapclient import IMAPClient
from odoo import api, fields, models, exceptions

from ..application.use_cases.backfill_folder_progressive import (
    BackfillFolderProgressive,
)
from ..application.use_cases.backfill_folder_progressive_gmail import (
    BackfillFolderProgressiveGmail,
)
from ..application.use_cases.backfill_folder_progressive_outlook import (
    BackfillFolderProgressiveOutlook,
)
from ..application.use_cases.bootstrap_folder import BootstrapFolder
from ..application.use_cases.bootstrap_folder_gmail import BootstrapFolderGmail
from ..application.use_cases.bootstrap_folder_outlook import BootstrapFolderOutlook
from ..application.services.imap_client_service import (
    build_authenticated_imap_client,
)
from ..infrastructure.adapters.bus_notification_adapter import BusNotificationAdapter
from ..infrastructure.providers.outlook.client_factory import (
    GRAPH_BASE_URL,
    get_outlook_client,
)
from ..infrastructure.utils.imap_encoding import (
    normalize_folder_name,
    safe_folder_operation,
)

_logger = logging.getLogger(__name__)

_MAILBOX_FOLDER_SYNC_LOCK_NAMESPACE = 48232

EXCLUDE_PARTS = {
    "calendar",
    "kalender",
    "contacts",
    "kontakte",
    "tasks",
    "aufgaben",
    "notes",
    "notizen",
    "journal",
    "public",
    "rss",
    "search",
    "conversation",
    "quick",
    "synchronisierungsprobleme",
    "sync",
    "serverfehler",
    "konflikte",
    "postausgang",
}


GMAIL_FOLDER_MAP = {
    "[Gmail]/Bin": "trash",
    "[Gmail]/Trash": "trash",
    "[Google Mail]/Bin": "trash",
    "[Google Mail]/Trash": "trash",
    "[Gmail]/Sent Mail": "sent",
    "[Google Mail]/Sent Mail": "sent",
    "[Gmail]/Drafts": "drafts",
    "[Google Mail]/Drafts": "drafts",
    "[Gmail]/Spam": "spam",
    "[Google Mail]/Spam": "spam",
    "[Gmail]/All Mail": "archive",
    "[Google Mail]/All Mail": "archive",
}

FOLDER_TYPE_SELECTION = [
    ("inbox", "Inbox"),
    ("starred", "Starred"),
    ("sent", "Sent"),
    ("drafts", "Drafts"),
    ("archive", "Archive"),
    ("spam", "Spam"),
    ("trash", "Trash"),
    ("other", "Other"),
]

SPECIAL_USE_MAP = {
    "\\inbox": "inbox",
    "\\sent": "sent",
    "\\drafts": "drafts",
    "\\junk": "spam",
    "\\spam": "spam",
    "\\trash": "trash",
    "\\archive": "archive",
    "\\all": "archive",
    "\\allmail": "archive",
    "\\flagged": "starred",
    "\\important": "starred",
}

FOLDER_SEQUENCE = {
    "inbox": 1,
    "starred": 2,
    "sent": 3,
    "drafts": 4,
    "archive": 5,
    "spam": 6,
    "trash": 7,
    "other": 90,
}

FOLDER_CODE_ALIASES = {
    # Trash
    "papierkorb": "trash",
    "trash": "trash",
    "bin": "trash",
    "deleted": "trash",
    "corbeille": "trash",
    "cestino": "trash",
    "eliminati": "trash",
    "borrados": "trash",
    "удаленные": "trash",
    "deleted messages": "trash",
    "gelöschte nachrichten": "trash",
    # Spam
    "junk": "spam",
    "spam": "spam",
    "correo no deseado": "spam",
    "нежелательная почта": "spam",
    # Starred
    "flagged": "starred",
    "important": "starred",
    "важное": "starred",
    # Sent
    "sent": "sent",
    "отправленные": "sent",
    "gesendet": "sent",
    "envoyés": "sent",
    "inviati": "sent",
    "enviados": "sent",
    "sent messages": "sent",
    "gesendete nachrichten": "sent",
    # Drafts
    "drafts": "drafts",
    "черновики": "drafts",
    "entwürfe": "drafts",
    "brouillons": "drafts",
    # Archive
    "archive": "archive",
    "archiv": "archive",
    "архив": "archive",
    "all_mail": "archive",
    "alle nachrichten": "archive",
    # Inbox
    "INBOX": "inbox",
    "inbox": "inbox",
    "входящие": "inbox",
    "eingang": "inbox",
    "réception": "inbox",
    "posta in arrivo": "inbox",
    "bandeja de entrada": "inbox",
}

GRAPH_FOLDER_SELECT = (
    "id,displayName,parentFolderId,childFolderCount,unreadItemCount,isHidden"
)

OUTLOOK_WELLKNOWN_MAP = {
    "inbox": "inbox",
    "sentitems": "sent",
    "drafts": "drafts",
    "deleteditems": "trash",
    "junkemail": "spam",
    "archive": "archive",
}


def is_real_mail_folder(folder):
    """
    Determine whether a Graph folder should be treated as a real mail folder by
    filtering out hidden entries, special system areas, and long technical names
    that likely belong to other services. Prevents cluttering the MailDesk UI
    with non-email folders.
    """
    if folder.get("isHidden") is True:
        return False

    name_l = (folder.get("displayName") or "").strip().lower()

    if any(part in name_l for part in EXCLUDE_PARTS):
        return False

    if (
        len(name_l) >= 30
        and "-" in name_l
        and all(c.isalnum() or c in "-_" for c in name_l)
    ):
        return False

    return True


def classify_folder(display_name):
    """
    Infer a canonical folder type code based on localized keywords in the
    display name, covering inbox, sent, drafts, spam, trash, archive, and a
    generic fallback. Helps map provider-specific names to consistent behavior.
    """
    name_l = (display_name or "").lower()

    if "inbox" in name_l or "входящие" in name_l or "eingang" in name_l:
        return "inbox"
    if "sent" in name_l or "gesendet" in name_l or "отправленные" in name_l:
        return "sent"
    if "draft" in name_l or "entwürfe" in name_l or "черновики" in name_l:
        return "drafts"
    if "spam" in name_l or "junk" in name_l or "нежелательная почта" in name_l:
        return "spam"
    if (
        "trash" in name_l
        or "deleted" in name_l
        or "gelöschte" in name_l
        or "удаленные" in name_l
        or "bin" in name_l
    ):
        return "trash"
    if "archive" in name_l or "archiv" in name_l or "архив" in name_l:
        return "archive"

    return "other"


def fetch_folder_tree(session):
    """
    Retrieve the Outlook folder hierarchy via Graph API, recursively loading
    children for folders deemed real mail folders. Returns a nested structure
    compatible with further processing and raises for HTTP errors to surface
    connectivity issues.
    """
    resp = session.get(
        f"{GRAPH_BASE_URL}/me/mailFolders",
        params={"$top": "100", "$select": GRAPH_FOLDER_SELECT},
    )
    resp.raise_for_status()
    roots = resp.json().get("value", [])

    def load_children(folder):
        """Recursively fetch child folders and keep only real mail folders."""
        fid = folder["id"]

        resp = session.get(
            f"{GRAPH_BASE_URL}/me/mailFolders/{fid}/childFolders",
            params={"$top": "100", "$select": GRAPH_FOLDER_SELECT},
        )
        resp.raise_for_status()

        children = []
        for child in resp.json().get("value", []):
            if is_real_mail_folder(child):
                child["children"] = load_children(child)
                children.append(child)

        return children

    tree = []
    for root in roots:
        if not is_real_mail_folder(root):
            continue
        root["children"] = load_children(root)
        tree.append(root)

    return tree


class MailboxFolder(models.Model):
    _name = "mailbox.folder"
    _description = "Mailbox Folder"
    _rec_name = "name"
    _order = "account_id, sequence, name"

    name = fields.Char(
        required=True,
        help="Human-readable name of the folder (e.g. Inbox, Trash).",
    )
    imap_name = fields.Char(
        index=True,
        readonly=True,
        store=True,
        help="Technical name of the folder on the server (e.g. INBOX, [Gmail]/Sent Mail).",
    )
    account_id = fields.Many2one("mailbox.account", required=True, ondelete="cascade")
    parent_id = fields.Many2one(
        "mailbox.folder",
        ondelete="cascade",
        help="Parent folder if this is a subfolder.",
    )
    child_ids = fields.One2many("mailbox.folder", "parent_id")
    is_visible = fields.Boolean(
        default=True,
        help="If unchecked, this folder will be hidden from the MailDesk sidebar.",
    )
    uid_validity = fields.Integer(default=0)
    last_uid = fields.Integer(
        string="Last UID",
        default=0,
        help="Last known UID for incremental sync (NOT used during backfill)",
    )

    # Phase 2 Sync Fields (Two-Phase Architecture)
    last_uidnext = fields.Integer(
        default=0,
        help="Last seen UIDNEXT from Scan phase. Used to detect new messages.",
    )
    last_highest_modseq = fields.Char(
        default="0",
        help="Last seen HIGHESTMODSEQ from Scan phase. Used to detect flag changes/deletions.",
    )
    needs_sync = fields.Boolean(
        default=False,
        index=True,
        help="Dirty flag set by Scan phase if folder HAS changes. Triggers targeted sync.",
    )

    sync_state = fields.Selection(
        [
            ("never_synced", "Never Synced"),
            ("backfill_pending", "Backfill Pending"),
            ("backfill_in_progress", "Backfill In Progress"),
            ("incremental", "Incremental"),
        ],
        default="never_synced",
        required=True,
        help="Folder backfill state machine. Ensures SSOT completeness.",
    )

    backfill_started_at = fields.Datetime(
        string="Backfill Started",
        help="When backfill began (for progress tracking and audit)",
    )

    backfill_completed_at = fields.Datetime(
        string="Backfill Completed",
        help="When backfill finished (for audit and SLA tracking)",
    )

    backfill_total_estimate = fields.Integer(
        string="Backfill Total (Estimate)",
        default=0,
        help="Estimated total messages to backfill (from UIDNEXT or label count)",
    )

    backfill_fetched_count = fields.Integer(
        default=0,
        help="Messages fetched so far during backfill (for progress tracking)",
    )

    backfill_last_uid = fields.Integer(
        string="Backfill Last UID",
        default=0,
        help="Last UID fetched during backfill (for resume after interruption)",
    )
    gmail_label_id = fields.Char(
        string="Gmail Label ID",
        help="Gmail label id used for backfill cursor mapping",
    )
    gmail_backfill_page_token = fields.Char(
        help="Gmail messages.list page token for progressive backfill",
    )
    outlook_graph_id = fields.Char(
        string="Outlook Graph Folder ID",
        help="Stable Graph folder id for Outlook delta folder mapping",
    )
    outlook_backfill_next_link = fields.Char(
        help="Graph @odata.nextLink cursor for progressive backfill",
    )

    # Computed fields for UI display
    backfill_progress = fields.Float(
        "Backfill Progress %",
        compute="_compute_backfill_progress",
        store=False,
        help="Percentage of messages fetched (0-100)",
    )

    backfill_status_display = fields.Char(
        "Backfill Status",
        compute="_compute_backfill_status",
        store=False,
        help="Human-readable status for UI (e.g., 'Complete', '420/1500')",
    )

    unread_count = fields.Integer(default=0)
    unread_count_updated_at = fields.Datetime(
        help="Timestamp of last unread count update (for caching)"
    )
    sequence = fields.Integer(
        default=100,
        compute="_compute_sequence",
        store=True,
        help="Sort order in the folder list. Low numbers appear first.",
    )
    sync_modseq = fields.Char(default="0")
    last_sync_at = fields.Datetime(index=True)
    last_error = fields.Text()
    folder_type = fields.Selection(
        FOLDER_TYPE_SELECTION,
        default="other",
        required=True,
        help="Logical type of the folder (Inbox, Sent, etc.). Controls icon and behavior.",
    )

    @api.depends("folder_type", "name")
    def _compute_sequence(self):
        """
        Compute display ordering based on folder type priority and hierarchy
        depth, ensuring nested folders sort predictably. Uses IMAP delimiter
        counts to approximate depth.
        """
        for folder in self:
            base = FOLDER_SEQUENCE.get(folder.folder_type or "other", 90)
            depth = (folder.imap_name or "").count("/") + (
                folder.imap_name or ""
            ).count("\\")
            folder.sequence = base * 10 + min(depth, 9)

    @api.depends(
        "backfill_total_estimate",
        "backfill_fetched_count",
        "sync_state",
        "backfill_completed_at",
    )
    def _compute_backfill_progress(self):
        """Calculate backfill progress percentage (0-100)"""
        for folder in self:
            if folder.sync_state == "incremental" and folder.backfill_completed_at:
                folder.backfill_progress = 100.0
            elif folder.backfill_total_estimate > 0:
                folder.backfill_progress = (
                    folder.backfill_fetched_count / folder.backfill_total_estimate
                ) * 100
            else:
                folder.backfill_progress = 0.0

    @api.depends(
        "sync_state",
        "backfill_fetched_count",
        "backfill_total_estimate",
        "backfill_completed_at",
    )
    def _compute_backfill_status(self):
        """Generate human-readable backfill status for UI"""
        for folder in self:
            if folder.sync_state == "backfill_pending":
                folder.backfill_status_display = "Pending..."
            elif folder.sync_state == "incremental" and folder.backfill_completed_at:
                folder.backfill_status_display = "✓ Complete"
            elif folder.backfill_total_estimate > 0:
                folder.backfill_status_display = (
                    f"{folder.backfill_fetched_count}/{folder.backfill_total_estimate}"
                )
            else:
                folder.backfill_status_display = "Unknown"

    @api.model
    def _try_acquire_folder_sync_lock(self, folder_id: int) -> bool:
        """
        Try to acquire an advisory transaction lock for a folder sync writer.

        This enforces folder-level mutual exclusion across bootstrap, progressive
        backfill, and incremental sync entrypoints running in parallel workers.

        Returns:
            bool: True when lock is acquired, False when another worker holds it.
        """
        try:
            fid = int(folder_id or 0)
        except (TypeError, ValueError):
            return False

        if fid <= 0:
            return False

        lock_key = (_MAILBOX_FOLDER_SYNC_LOCK_NAMESPACE << 32) | (fid & 0xFFFFFFFF)
        self.env.cr.execute("SELECT pg_try_advisory_xact_lock(%s)", (int(lock_key),))
        row = self.env.cr.fetchone()
        return bool(row and row[0])

    @api.model
    def sync_folders_for_account(self, account):
        """
        Synchronize folder records for the given account using Outlook Graph or
        IMAP depending on server type, ensuring the Inbox exists before syncing
        the full tree. Runs with sudo to bypass access restrictions on server
        metadata.
        """
        self = self.sudo()
        srv = account.mail_server_id.sudo()
        if srv.server_type == "outlook":
            return self._sync_outlook_graph(account)

        with build_authenticated_imap_client(self.env, account) as client:
            self._ensure_inbox(client, account)
            self._sync_all(client, account)
        if self.env.context.get("maildesk_bootstrap_after_folder_sync"):
            self.bootstrap_if_pending()

    @api.model
    def bootstrap_if_pending(self):
        """
        Bootstrap all folders in backfill_pending state.
        Called from cron worker to trigger initial message fetch.

        This is the ENTRY POINT that transitions folders from
        backfill_pending → incremental and populates message_index.
        """
        folders = self.search([("sync_state", "=", "backfill_pending")], limit=10)

        for folder in folders:
            try:
                if not self._try_acquire_folder_sync_lock(folder.id):
                    continue

                for attempt in range(3):
                    try:
                        with self.env.cr.savepoint():
                            account = folder.account_id
                            if account.is_gmail:
                                use_case = BootstrapFolderGmail(self.env)
                            elif account.is_outlook:
                                use_case = BootstrapFolderOutlook(self.env)
                            else:
                                use_case = BootstrapFolder(self.env)

                            use_case.execute(folder.id)
                        break
                    except psycopg2.errors.SerializationFailure:
                        if attempt < 2:
                            continue
                        raise
            except psycopg2.errors.SerializationFailure:
                raise
            except Exception as e:
                _logger.error(
                    f"Bootstrap failed for folder {folder.id}: {e}", exc_info=True
                )

    def progressive_backfill(self):
        """
        Phase 5.2: Run one slice of progressive backfill for folders.
        Called from cron worker.
        """
        for folder in self:
            if folder.sync_state == "incremental" and not folder.backfill_completed_at:
                try:
                    if not self._try_acquire_folder_sync_lock(folder.id):
                        continue

                    for attempt in range(3):
                        try:
                            with self.env.cr.savepoint():
                                account = folder.account_id
                                if account.is_gmail:
                                    use_case = BackfillFolderProgressiveGmail(self.env)
                                elif account.is_outlook:
                                    use_case = BackfillFolderProgressiveOutlook(
                                        self.env
                                    )
                                else:
                                    use_case = BackfillFolderProgressive(self.env)

                                use_case.execute(folder.id)
                            break
                        except psycopg2.errors.SerializationFailure:
                            if attempt < 2:
                                continue
                            raise
                except psycopg2.errors.SerializationFailure:
                    raise
                except Exception as e:
                    _logger.error(
                        f"Progressive backfill failed for folder {folder.id}: {e}",
                        exc_info=True,
                    )

    def trigger_backfill(self):
        """Manually trigger backfill for selected folders."""
        self.ensure_one()

        if not self._try_acquire_folder_sync_lock(self.id):
            raise exceptions.UserError(
                self.env._(
                    "This folder is currently being synchronized. Please try again shortly."
                )
            )

        if self.sync_state != "incremental":
            raise exceptions.UserError(
                self.env._(
                    "Can only trigger backfill for folders in incremental state.\n"
                    "Current state: "
                )
                + str(self.sync_state)
            )

        # Reset backfill state
        self.write(
            {
                "backfill_last_uid": 0,
                "backfill_fetched_count": 0,
                "backfill_started_at": False,
                "backfill_completed_at": False,
            }
        )

        # Trigger progressive backfill
        account = self.account_id
        if account.is_gmail:
            use_case = BackfillFolderProgressiveGmail(self.env)
        elif account.is_outlook:
            use_case = BackfillFolderProgressiveOutlook(self.env)
        else:
            use_case = BackfillFolderProgressive(self.env)

        use_case.execute(self.id)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Backfill Started",
                "message": f"Fetching older messages for {self.name}...",
                "type": "success",
                "sticky": False,
            },
        }

    def _ensure_inbox(self, client, account):
        """
        Ensure an Inbox record exists and update its UID validity, last UID, and
        unread counters based on IMAP status. Creates the folder if missing to
        guarantee baseline synchronization.

        Phase 5.1: CRITICAL FIX - Initialize last_uid to 0 (not UIDNEXT-1)
        to enable full historical backfill instead of skipping pre-existing messages.
        """
        status = client.folder_status("INBOX", ["UIDVALIDITY", "UIDNEXT", "UNSEEN"])
        uidv = status.get(b"UIDVALIDITY", 0)
        unseen = int(status.get(b"UNSEEN", 0))
        inbox = self.search(
            [("account_id", "=", account.id), ("imap_name", "=", "INBOX")], limit=1
        )
        if not inbox:
            inbox = self.create(
                {
                    "name": "INBOX",
                    "imap_name": "INBOX",
                    "folder_type": "inbox",
                    "account_id": account.id,
                    "uid_validity": int(uidv or 0),
                    "last_uid": 0,
                    "unread_count": unseen,
                    "sync_state": "backfill_pending",
                }
            )

    def _sync_all(self, client, account):
        """
        Synchronize all IMAP folders for an account by listing folders, filtering
        out non-mail entries, querying status for unread counts, and creating or
        updating local records. Returns a summary of created and updated folders
        along with a mapping by IMAP name.
        """
        entries = client.list_folders() or []
        if not entries:
            return {"created": 0, "updated": 0, "total": 0, "by_name": {}}

        nodes = {}
        for flags, delim_char, raw_name in entries:
            # Use universal encoding utility for robust UTF-8 handling
            imap_name = normalize_folder_name(raw_name)
            if not imap_name:
                continue

            delim_char = (
                delim_char.decode()
                if isinstance(delim_char, bytes)
                else (delim_char or "/")
            )
            label = imap_name.rsplit(delim_char, 1)[-1].strip()
            if not label:
                continue

            label_l = label.lower()
            if any(p in label_l for p in EXCLUDE_PARTS):
                continue

            norm_flags = [self._norm_flag(f) for f in (flags or [])]
            if "\\noselect" in norm_flags:
                continue
            try:
                status = (
                    client.folder_status(
                        imap_name, ["UIDVALIDITY", "UIDNEXT", "UNSEEN"]
                    )
                    or {}
                )
            except IMAPClient.Error as err:  # narrow exception type
                _logger.warning("Skipping folder %s: %s", imap_name, err)
                continue

            # Use safe_folder_operation wrapper for robust error handling
            def get_status():
                return (
                    client.folder_status(
                        imap_name, ["UIDVALIDITY", "UIDNEXT", "UNSEEN"]
                    )
                    or {}
                )

            status = safe_folder_operation("STATUS", imap_name, get_status)
            if not status:
                # STATUS failed - skip this folder but continue with others
                _logger.info(f"Skipping folder '{imap_name}' - STATUS not supported")
                continue

            uidv = int(status.get(b"UIDVALIDITY", 0))
            unseen = int(status.get(b"UNSEEN", 0))

            if delim_char in imap_name:
                parent_path = delim_char.join(imap_name.split(delim_char)[:-1]) or False
            else:
                parent_path = False

            nodes[imap_name] = {
                "imap_name": imap_name,
                "label": label,
                "label_l": label_l,
                "delim_char": delim_char,
                "flags": flags,
                "norm_flags": norm_flags,
                "uid_validity": uidv,
                "unseen": unseen,
                "parent_path": parent_path,
            }

        existing = self.search([("account_id", "=", account.id)])
        rec_cache = {f.imap_name: f for f in existing}

        created = 0
        updated = 0

        def _ensure_folder(imap_name):
            """
            Recursively create or update folders to mirror the IMAP hierarchy,
            building parent folders as needed and updating caches for later
            lookups. Tracks counts of created and updated records.
            """
            nonlocal created, updated
            if not imap_name:
                return self.env["mailbox.folder"]
            if imap_name in rec_cache:
                return rec_cache[imap_name]

            data = nodes.get(imap_name)
            if not data:
                return self.env["mailbox.folder"]

            parent_rec = (
                _ensure_folder(data["parent_path"])
                if data["parent_path"]
                else self.env["mailbox.folder"]
            )

            vals = {
                "name": data["label"],
                "imap_name": data["imap_name"],
                "account_id": account.id,
                "unread_count": data["unseen"],
                "parent_id": parent_rec.id or False,
                "delim_char": data["delim_char"],
                "special_use_flags": data["flags"],
            }

            existing = self.search(
                [
                    ("account_id", "=", account.id),
                    ("imap_name", "=", data["imap_name"]),
                ],
                limit=1,
            )

            if existing:
                # Folder discovery MUST NOT update sync cursors.
                vals.pop("name", None)
                existing.write(vals)
                rec = existing
                updated += 1
            else:
                # Initialize sync cursors only for brand new folders.
                vals["uid_validity"] = data["uid_validity"]
                vals["last_uid"] = 0
                vals["sync_state"] = "backfill_pending"
                rec = self.create(vals)
            return rec

        for imap_name in nodes.keys():
            _ensure_folder(imap_name)

        # Detect deletions: folders in DB but not on server
        server_names = set(nodes.keys())
        db_names = {f.imap_name for f in existing}
        deleted_names = db_names - server_names

        if deleted_names:
            to_delete = self.search(
                [
                    ("account_id", "=", account.id),
                    ("imap_name", "in", list(deleted_names)),
                ]
            )
            to_delete.unlink()

        # Emit folder_tree_changed event if changes detected
        if created > 0 or updated > 0 or deleted_names:
            try:
                notifier = BusNotificationAdapter(self.env)
                all_folders = self.search([("account_id", "=", account.id)])
                folders_data = [
                    {
                        "id": f.id,
                        "name": f.name,
                        "imap_name": f.imap_name,
                    }
                    for f in all_folders
                ]
                notifier.notify_folder_tree_changed(
                    account_id=account.id,
                    folders=folders_data,
                )
            except Exception as e:
                _logger.error(f"[Folder Sync] Failed to emit folder_tree_changed: {e}")

        return {
            "created": created,
            "updated": updated,
            "total": len(rec_cache),
            "by_name": {k: v.id for k, v in rec_cache.items()},
        }

    @api.model
    def get_folder_tree(self, account_id, domain=None):
        # Fetch Real Unread Counts from SSOT (Group By)
        # This guarantees that the Sidebar matches the Mail List 100%
        sql = """
            SELECT folder, count(id)
            FROM maildesk_message_index
            WHERE account_id = %s AND is_read = false
            GROUP BY folder
        """
        self.env.cr.execute(sql, (account_id,))
        # Map: folder_imap_name -> count
        unread_map = dict(self.env.cr.fetchall())

        folders = self.search(
            [("account_id", "=", account_id), ("is_visible", "=", True)]
        )
        root = folders.filtered(lambda f: not f.parent_id)
        return [self._serialize(f, unread_map) for f in root.sorted("sequence")]

    def _serialize(self, folder, unread_map=None):
        """
        Convert a folder record into a dict with children recursively serialized
        for frontend consumption. Includes unread counts and folder type for UI
        rendering.
        """
        # Override stored count with real count if available
        real_count = folder.unread_count
        if unread_map is not None and folder.imap_name:
            real_count = unread_map.get(folder.imap_name, 0)

        return {
            "id": folder.id,
            "name": folder.name,
            "imap_name": folder.imap_name,
            "unread_count": real_count,
            "children": [
                self._serialize(c, unread_map)
                for c in folder.child_ids.sorted("sequence")
            ],
            "folder_type": folder.folder_type,
        }

    def _norm_flag(self, f):
        """
        Normalize IMAP flag values to lowercase strings regardless of byte or
        str input so downstream comparisons are reliable.
        """
        if isinstance(f, bytes):
            f = f.decode(errors="ignore")
        return (f or "").strip().lower()

    @api.model
    def _classify_folder(self, flags, delim, imap_name):
        """
        Determine a folder type from special-use flags, Gmail-specific mappings,
        or heuristics based on the label or IMAP path. Provides consistent codes
        for standard folders even across localized names.
        """
        norm_flags = [self._norm_flag(f) for f in (flags or [])]
        for f in norm_flags:
            code = SPECIAL_USE_MAP.get(f)
            if code:
                return code
        if "flagged" in norm_flags or "important" in norm_flags:
            return "starred"

        if imap_name in GMAIL_FOLDER_MAP:
            return GMAIL_FOLDER_MAP[imap_name]

        delim = delim or "/"
        label = (
            imap_name.split(delim)[-1]
            if delim in (imap_name or "")
            else (imap_name or "")
        )
        label_l = (label or "").strip().lower()

        if (imap_name or "").upper() == "INBOX" or label_l == "inbox":
            return "inbox"

        code = FOLDER_CODE_ALIASES.get(label_l)
        if code:
            return code

        for known, code in [
            ("sent", "sent"),
            ("draft", "drafts"),
            ("spam", "spam"),
            ("junk", "spam"),
            ("trash", "trash"),
            ("bin", "trash"),
            ("archive", "archive"),
            ("all mail", "archive"),
            ("starred", "starred"),
        ]:
            if known in label_l:
                return code

        return "other"

    @api.model_create_multi
    def create(self, vals_list):
        """
        Create folder records while classifying their types from IMAP metadata
        and discarding transient sync hints. Ensures stored records carry stable
        folder_type values before delegating to the parent create.
        """
        for vals in vals_list:
            imap_name = vals.get("imap_name") or ""
            delim = vals.get("delim_char") or "/"
            flags = vals.get("special_use_flags") or []
            if not vals.get("folder_type"):
                ftype = self._classify_folder(flags, delim, imap_name)
                vals["folder_type"] = ftype or "other"
            vals.pop("delim_char", None)
            vals.pop("special_use_flags", None)
        records = super().create(vals_list)
        return records

    def write(self, vals):
        """
        Update folders while reclassifying types when relevant fields change and
        stripping temporary sync hints that should not be persisted. Falls back
        to normal writes when folder_type is provided explicitly.
        """
        if "folder_type" in vals:
            vals.pop("delim_char", None)
            vals.pop("special_use_flags", None)
            return super().write(vals)

        need_reclass = False
        for key in ("imap_name", "delim_char", "special_use_flags", "name"):
            if key in vals:
                need_reclass = True
                break

        if need_reclass:
            for rec in self:
                imap_name = vals.get("imap_name", rec.imap_name or "")
                delim = vals.get("delim_char") or "/"
                flags = vals.get("special_use_flags") or []
                ftype = (
                    self._classify_folder(flags, delim, imap_name)
                    or rec.folder_type
                    or "other"
                )

                local_vals = dict(vals)
                local_vals["folder_type"] = ftype
                local_vals.pop("delim_char", None)
                local_vals.pop("special_use_flags", None)
                super(MailboxFolder, rec).write(local_vals)
            return True

        vals.pop("delim_char", None)
        vals.pop("special_use_flags", None)
        return super().write(vals)

    @api.model
    def _sync_outlook_graph(self, account):
        """
        Synchronize Outlook folders via Graph API by building a nested tree,
        mapping well-known names to canonical types, and creating or updating
        local records with unread counts. Returns a summary of creation and
        update statistics.
        """
        session, _base_url = get_outlook_client(self.env, account)
        raw_roots = fetch_folder_tree(session)

        def build_node(folder, parent_path=""):
            """
            Transform a Graph folder JSON node into a simplified dict containing
            name, path, unread count, type, and recursively built children.
            """
            name = (folder.get("displayName") or "").strip()
            if not name:
                return None

            path = f"{parent_path}/{name}" if parent_path else name
            well_known = (folder.get("wellKnownName") or "").lower()
            if well_known in OUTLOOK_WELLKNOWN_MAP:
                folder_type = OUTLOOK_WELLKNOWN_MAP[well_known]
            else:
                folder_type = classify_folder(name)

            node = {
                "name": name,
                "path": path,
                "unread": int(folder.get("unreadItemCount") or 0),
                "folder_type": folder_type,
                "graph_id": folder.get("id"),
                "children": [],
            }

            for child in folder.get("children") or []:
                child_node = build_node(child, parent_path=path)
                if child_node:
                    node["children"].append(child_node)

            return node

        root_nodes = []
        for raw in raw_roots:
            node = build_node(raw, parent_path="")
            if node:
                root_nodes.append(node)

        existing = self.search([("account_id", "=", account.id)])
        rec_by_path = {f.imap_name: f for f in existing}

        created = updated = 0

        def ensure_folder(node, parent_rec=False):
            """
            Create or update folders in Odoo matching the provided node tree,
            linking children to parents and tallying how many records were
            touched. Updates cached dictionary to avoid duplicate queries.
            """
            nonlocal created, updated
            if not node:
                return

            path = node["path"]
            rec = rec_by_path.get(path)

            vals = {
                "name": node["name"],
                "imap_name": path,
                "account_id": account.id,
                "unread_count": node["unread"],
                "parent_id": parent_rec.id if parent_rec else False,
                "folder_type": node["folder_type"],
                "outlook_graph_id": node.get("graph_id") or False,
            }

            if rec:
                rec.write(vals)
                updated += 1
            else:
                vals["sync_state"] = "backfill_pending"
                rec = self.create(vals)
                created += 1

            rec_by_path[path] = rec

            for child in node["children"]:
                ensure_folder(child, rec)

        for root in root_nodes:
            ensure_folder(root, parent_rec=False)

        return {
            "created": created,
            "updated": updated,
            "total": len(rec_by_path),
        }
