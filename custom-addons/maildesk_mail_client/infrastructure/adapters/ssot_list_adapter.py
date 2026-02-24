# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk SSOT List Adapter.

Implements infrastructure integration for SSOT List Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

import logging

from odoo import SUPERUSER_ID, fields

from ...application.services.display_formatting import (
    format_sender_display,
)
from ...application.services.sender_identity import SenderIdentityService
from ...domain.services.normalization import safe_dt
from ..rendering.html_sanitizer import strip_html_to_text
from ..rendering.ui_formatting import (
    avatar_html,
    display_name_from_email,
)

_logger = logging.getLogger(__name__)


class SsotListMessagesAdapter:
    """
    SSOT read-path adapter using maildesk.message_index (via MessageIndexQueryRepo).

    Clean Architecture:
    - Injects MessageIndexQueryRepo for all list queries
    - NO direct ORM access
    - Single-query list fetches (no overlays, no tag merges)
    """

    def __init__(self, env, query_repo):
        """
        Args:
            env: Odoo environment
            query_repo: MessageIndexQueryRepo (for CQRS read-side)
        """
        self._env = env
        self._query_repo = query_repo

    # Environment / access
    def registry_ready(self) -> bool:
        """Return True when the SSOT list path can safely run.

        `registry.ready` is only True after full module load/upgrade. During
        tests or upgrades, list RPCs can run while tables already exist but the
        registry is not marked ready yet. In that case we allow the list path
        when the SSOT table exists.
        """
        try:
            if bool(getattr(self._env.registry, "ready", False)):
                return True
            self._env.cr.execute("SELECT to_regclass('maildesk_message_index')")
            return bool(self._env.cr.fetchone()[0])
        except Exception:
            return False

    # Folder / account retrieval
    def folder_browse(self, folder_id: int):
        return self._env["mailbox.folder"].browse(folder_id)

    def folder_exists(self, folder) -> bool:
        return bool(folder and folder.exists())

    def folder_account(self, folder):
        return folder.account_id

    def folder_imap_name(self, folder):
        return getattr(folder, "imap_name", None)

    def folder_display_name(self, folder):
        return getattr(folder, "name", None)

    def folder_type(self, folder):
        return getattr(folder, "folder_type", None) or ""

    # Account selection
    def accounts_for_id(self, account_id: int):
        return self._env["mailbox.account"].browse([account_id])

    def user_accounts(self):
        return self._env["mailbox.account"].search(
            [("access_user_ids", "in", self._env.user.id)]
        )

    # Provider routing
    def is_gmail_account(self, account) -> bool:
        return account.is_gmail if account else False

    def is_outlook_account(self, account) -> bool:
        return account.is_outlook if account else False

    def _index_model(self):
        return self._env["maildesk.message_index"].sudo()

    def _ui_cache_model(self):
        return self._env["maildesk.ui_cache"].sudo()

    def has_any_indexed(self, account, folder_name, provider=None):
        domain = [
            ("account_id", "=", account.id),
        ]
        if folder_name is not None:
            if isinstance(folder_name, (list, tuple, set)):
                folders = [str(f).strip() for f in folder_name if f and str(f).strip()]
                if folders:
                    domain.append(("folder", "in", folders))
            else:
                domain.append(("folder", "=", folder_name))
        # IMPORTANT: Do not filter by provider for list-path existence checks.
        return bool(self._index_model().search(domain, limit=1))

    def _resolve_email_from(self, partner_id, email_from):
        """Resolve the email filter used for partner-scoped list searches.

        Priority:
        1) If an explicit `email_from` is provided, return it as-is.
        2) Otherwise, if `partner_id` is provided, derive the filter via
           `res.partner._maildesk_email_match()` (email for contacts, domain for
           companies).
        3) If neither is available, return None.
        """
        if email_from:
            return email_from
        if partner_id:
            partner = self._env["res.partner"].browse(partner_id)
            if partner.exists():
                return partner._maildesk_email_match()
        return None

    def search_index_records(self, account, folder_name, provider, params):
        """
        Single-query search using MessageIndexQueryRepo.

        Clean Architecture: Delegates to repository (no SQL/ORM here).
        Returns: (index_records, total_count)
        """
        email_from = self._resolve_email_from(params.partner_id, params.email_from)

        # Build search parameters
        search_term = None
        if params.search:
            search_term = params.search.strip() or None

        # CRITICAL FIX: Pass email_filter separately, do NOT concatenate
        # This ensures (Search AND Partner) logic works correctly

        # Determine sorting flags
        unread_first = params.filter == "unread"
        starred_first = params.filter == "starred"

        direction = (params.filter or "").strip().lower()
        if direction not in {"incoming", "outgoing"}:
            direction = None

        # Folder selection is always respected when provided (intersection semantics).
        # Direction filters further refine the selected folder scope.
        # Use folder_name directly (no derived "effective" variable).

        # Tag filtering (if provided)
        tag_ids = params.tag_ids if params.tag_ids else None

        # Single-query repository call
        index_records, total = self._query_repo.search_for_list(
            account_id=account.id,
            folder=folder_name,
            provider=provider,
            account_email=getattr(account, "email", None),
            direction=direction,
            offset=params.offset,
            limit=params.limit,
            tag_ids=tag_ids,
            search_term=search_term,
            email_filter=email_from,  # Pass separately
            unread_first=unread_first,
            starred_first=starred_first,
        )

        return index_records, total

    def build_records_from_index(self, account, folder, index_records, partner_cache):
        """
        Build UI DTOs from message_index records.

        CRITICAL: message_index is SSOT - its data takes precedence.
        Overlay UI-specific fields (avatars, partner info) on top.
        """
        if not index_records:
            return []

        # When listing at account-level (no selected folder), we still need a
        # correct folder context per message:
        # - display identity (Sent shows recipient, with correct avatar)
        # - correct folder_id for actions/opening messages
        #
        # Relying on folder-name heuristics is not enough because folder names can
        # be localized (e.g. "sent") and won't match "sent".
        folder_map = None
        if not folder and account:
            Folder = self._env["mailbox.folder"].sudo()
            folders = Folder.search([("account_id", "=", account.id)])
            folder_map = {}
            for f in folders:
                for key in [(f.imap_name or ""), (f.name or "")]:
                    k = str(key).strip().lower()
                    if k and k not in folder_map:
                        folder_map[k] = f

        # Initialize Canonical Sender Service with Cached Deps
        # using local partner_cache for efficiency
        deps = _CachedSenderIdentityDeps(self, self._env, partner_cache)

        sender_service = SenderIdentityService(deps)

        cache_map = self._ui_cache_model().fetch_for_index_records(index_records)
        records = []
        for idx_rec in index_records:
            record_folder = folder
            if not record_folder and folder_map is not None:
                k = str(getattr(idx_rec, "folder", "") or "").strip().lower()
                record_folder = folder_map.get(k)

            # SSOT data - this is the FOUNDATION (must not be overridden)
            base_rec = {
                "id": idx_rec.id,
                "uid": idx_rec.uid,
                "message_id_norm": idx_rec.message_id or "",
                "subject": idx_rec.subject or "(No Subject)",
                "from_addr": idx_rec.from_addr or "",
                "to_addrs": idx_rec.to_addrs or "",
                "date": idx_rec.date,
                "preview": idx_rec.preview or "",
                "has_attachments": idx_rec.has_attachments,
                "is_read": idx_rec.is_read,
                "is_starred": idx_rec.is_starred,
                # Denormalized tags (CQRS read model - no JOIN needed)
                # Format as objects for frontend consumption
                "tag_ids": [
                    {"id": t.id, "name": t.name, "color": t.color}
                    for t in idx_rec.tag_ids
                ],
                # Denormalized pending operations
                "pending_move_to": idx_rec.pending_move_to,
                "pending_delete": idx_rec.pending_delete,
            }

            # UI-specific fields (avatars, formatted dates, partner info)
            # These are OVERLAID on top of SSOT, NOT the other way around
            ui_enhancements = self._record_from_index(
                account, record_folder, idx_rec, partner_cache, sender_service
            )

            # CORRECT merge order: base SSOT data, then UI enhancements
            record = {}
            record.update(ui_enhancements)  # UI fields first
            record.update(base_rec)  # SSOT data OVERRIDES UI defaults

            # Cache overlays (ONLY for UI artifacts, NOT SSOT metadata)
            cached = cache_map.get(idx_rec.id)
            cache_json = cached.json_cache or {} if cached else {}

            # Allowed: these are UI-only artifacts.
            if cache_json.get("avatar_html"):
                record["avatar_html"] = cache_json["avatar_html"]
            if cache_json.get("avatar_partner_id"):
                record["avatar_partner_id"] = cache_json["avatar_partner_id"]

            if cache_json.get("preview_text"):
                record["preview_text"] = cache_json["preview_text"]

            records.append(record)

        return records

    def apply_state_overlays(self, account, folder_name, records):
        """
        DEPRECATED: Phase 3 Clean Architecture refactor.

        State is now denormalized in message_index (pending_move_to, pending_delete).
        UI must NOT call this method.
        """
        raise NotImplementedError(
            "apply_state_overlays is deprecated. "
            "State is denormalized in message_index. "
            "Use MessageIndexQueryRepo for list queries."
        )

    def apply_overrides_and_tags(self, account, folder, records, total, tag_ids):
        """
        DEPRECATED: Phase 3 Clean Architecture refactor.

        Tags are now denormalized in message_index.tag_ids.
        Tag filtering is handled at SQL level via MessageIndexQueryRepo.
        """
        raise NotImplementedError(
            "apply_overrides_and_tags is deprecated. "
            "Tags are denormalized in message_index.tag_ids. "
            "Use MessageIndexQueryRepo with tag_ids parameter."
        )

    def get_tags_for_message_ids(self, account_id, msg_ids):
        """
        DEPRECATED: Phase 3 Clean Architecture refactor.

        Tags are preloaded via index_records.tag_ids (Many2many).
        No separate query needed.
        """
        raise NotImplementedError(
            "get_tags_for_message_ids is deprecated. "
            "Tags are preloaded in index_records.tag_ids. "
            "Access via record['tag_ids']."
        )

    def append_local_drafts(self, account, folder, records, total, search):
        Draft = self._env["maildesk.draft"].sudo()
        domain = [
            ("account_id", "=", account.id),
            # Drafts are normally per-user, but older versions could have saved
            # them under the superuser due to `.sudo()` semantics. Include those
            # so they remain visible and can be claimed on next save.
            ("user_id", "in", [self._env.user.id, SUPERUSER_ID]),
        ]
        if search:
            s = search.strip()
            if s:
                domain += [
                    "|",
                    "|",
                    ("subject", "ilike", s),
                    ("to_emails", "ilike", s),
                    ("body_html", "ilike", s),
                ]

        total_local = Draft.search_count(domain)
        drafts = Draft.search(domain, order="write_date desc, id desc")

        for d in drafts:
            dt = d.write_date or d.create_date
            if dt:
                dt_ctx = fields.Datetime.context_timestamp(
                    self._env["mailbox.sync"], dt
                )
                formatted_date = dt_ctx.strftime("%d %b %Y %H:%M")
            else:
                formatted_date = ""

            sort_ts = int(dt.timestamp()) if dt else 0
            preview_src = d.body_html or ""
            preview = strip_html_to_text(preview_src)[:120]

            email_from_val = (account.email or "").lower()

            to_list = [x.strip() for x in (d.to_emails or "").split(",") if x.strip()]
            cc_list = [x.strip() for x in (d.cc_emails or "").split(",") if x.strip()]
            bcc_list = [x.strip() for x in (d.bcc_emails or "").split(",") if x.strip()]

            records.append(
                {
                    "id": d.id,
                    "account_id": [account.id, account.name],
                    "folder_id": folder.id,
                    "subject": d.subject or "",
                    "email_from": email_from_val,
                    "sender_display_name": (
                        d.sender_display_name
                        or format_sender_display(
                            account.sender_name or account.name, email_from_val
                        )
                    ),
                    "date": dt,
                    "sort_ts": sort_ts,
                    "is_internal_draft": True,
                    "formatted_date": formatted_date,
                    "is_read": False,
                    "is_draft": True,
                    "is_starred": False,
                    "tag_ids": [
                        {"id": t.id, "name": t.name, "color": t.color}
                        for t in d.tag_ids
                    ],
                    "has_attachments": bool(d.attachment_ids),
                    "to_display": ", ".join(to_list),
                    "cc_display": ", ".join(cc_list),
                    "bcc_display": ", ".join(bcc_list),
                    "preview_text": preview,
                    "avatar_html": avatar_html(
                        email_from_val, d.user_id.partner_id, display_name_from_email
                    ),
                    "avatar_partner_id": d.user_id.partner_id.id,
                    "message_id_norm": d.message_id or "",
                    "is_local_draft": True,
                    "msg_key": f"{account.id}|{folder.id if folder else ''}|draft|{d.id}",
                }
            )

        return records, total + total_local

    def safe_dt(self, rec):
        return safe_dt(rec)

    def resolve_inbox_folder(self, account):
        Folder = self._env["mailbox.folder"]
        return (
            Folder.search(
                [("account_id", "=", account.id), ("imap_name", "=", "INBOX")], limit=1
            )
            or Folder.search(
                [("account_id", "=", account.id), ("name", "=", "INBOX")], limit=1
            )
            or Folder.browse(False)
        )

    def _record_from_index(
        self, account, folder, idx, partner_cache, sender_service=None
    ):
        """
        Build UI record from message_index (SSOT).

        CRITICAL: For sent folders, display RECIPIENT instead of sender.
        Using Canonical Sender Service.
        """
        # Resolve Visual Identity
        if sender_service:
            folder_name_heuristic = idx.folder
            # If we cannot reliably resolve folder type (e.g. account-level view),
            # fall back to "sent-style" rendering when the message is clearly
            # outgoing from this account (From matches account email).
            try:
                acc_email = (getattr(account, "email", "") or "").strip().lower()
                from_addr_l = (idx.from_addr or "").strip().lower()
                if acc_email and from_addr_l and acc_email in from_addr_l:
                    if not folder or (self.folder_type(folder) or "") in {"", "other"}:
                        folder_name_heuristic = "sent"
            except Exception:
                folder_name_heuristic = idx.folder

            identity = sender_service.resolve_visual_identity(
                from_addr=idx.from_addr or "",
                to_addrs=idx.to_addrs or "",
                sender_display_name_header=idx.sender_display_name
                or idx.from_addr
                or "",
                folder=folder,
                folder_name_heuristic=folder_name_heuristic,
            )
            display_email = identity["visual_email"]
            sender_display = identity["sender_display_name"]
            avatar_html_content = identity["avatar_html"]
            avatar_partner_id = identity["avatar_partner_id"]
            partner_trusted = identity["partner_trusted"]
            content_trusted = identity.get("content_trusted")
            folder_type = identity["folder_type"]
        else:
            # Fallback (Should not happen after refactor, but safe guard)
            display_email = idx.from_addr or ""
            sender_display = idx.sender_display_name or ""
            avatar_html_content = ""
            avatar_partner_id = False
            partner_trusted = False
            content_trusted = False
            folder_type = "other"

        formatted_date = ""
        if idx.date:
            try:
                dt_ctx = fields.Datetime.context_timestamp(self._env.user, idx.date)
                formatted_date = dt_ctx.strftime("%d %b %Y %H:%M")
            except Exception:
                formatted_date = ""

        preview_text = idx.preview or ""

        uid = str(idx.uid or "")
        folder_id = folder.id if folder else False
        msg_key = f"{account.id}|{folder_id if folder else ''}|{uid}"

        record = {
            "id": idx.id,  # Use SSOT Database ID (critical for direct RPC actions)
            "uid": uid,
            "sort_ts": int(idx.sort_ts or 0),
            "account_id": [account.id, account.name],
            "folder_id": folder_id,
            "folder": idx.folder,
            "folder_name": idx.folder,
            "folder_type": folder_type,
            "subject": idx.subject or "(no subject)",
            "visual_email": display_email,  # Explicit Visual Email
            "email_from": display_email,  # Legacy UI Alias (Visual) - CRITICAL for frontend
            "from_addr": idx.from_addr or "",  # Technical (Immutable)
            "sender_display_name": sender_display,
            "date": idx.date or False,
            "formatted_date": formatted_date,
            "avatar_html": avatar_html_content,
            "is_read": bool(idx.is_read),
            "is_starred": bool(idx.is_starred),
            "is_draft": "\\draft" in (idx.flags or "").lower(),
            "has_attachments": bool(idx.has_attachments),
            "preview_text": preview_text,
            "preview": preview_text,
            "to_display": idx.to_addrs or "",
            "cc_display": idx.cc_addrs or "",
            "bcc_display": idx.bcc_addrs or "",
            "avatar_partner_id": avatar_partner_id,
            "partner_trusted": partner_trusted,
            "content_trusted": bool(content_trusted),
            "tag_ids": [
                {"id": t.id, "name": t.name, "color": t.color} for t in idx.tag_ids
            ],
            "message_id_norm": idx.message_id or "",
            "in_reply_to": idx.in_reply_to or "",
            "references_hdr": idx.references_hdr or "",
            "thread_id": idx.thread_id or "",
            "msg_key": msg_key,
            "backend_type": idx.provider or "imap",
        }
        return record


class _CachedSenderIdentityDeps:
    """Helper to provide dependencies to SenderIdentityService with caching."""

    def __init__(self, adapter, env, partner_cache):
        self.adapter = adapter
        self.env = env
        self.cache = partner_cache

    def partner_search(self, email):
        if not email:
            return self.env["res.partner"].browse(False)
        p = self.cache.get(email)
        if p is None:
            p = self.env["res.partner"].search([("email", "=ilike", email)], limit=1)
            self.cache[email] = p
        return p

    def avatar_html(self, email, partner):
        return avatar_html(email, partner, display_name_from_email)

    def folder_type(self, folder):
        return self.adapter.folder_type(folder)
