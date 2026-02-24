# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Open Message Adapter.

Implements infrastructure integration for Open Message Adapter (I/O, providers, persistence, or adapters).
Layer: infrastructure.
"""

from __future__ import annotations

from typing import Any, Dict, List

from odoo import fields

from ...domain.services.normalization import (
    addr_to_email,
    decode_header_value,
    join_addresses,
    norm_msgid,
    to_datetime,
)
from ...infrastructure.rendering.cid_rewriter import replace_cid_src
from ...infrastructure.rendering.html_sanitizer import (
    sanitize_email_html,
    strip_html_to_text,
)
from ...infrastructure.rendering.ui_formatting import (
    avatar_html,
    display_name_from_email,
)
from ...application.services.display_formatting import format_sender_display
from ..providers.gmail.auth import gmail_build_service
from ..providers.gmail.message_provider import gmail_get_message_full
from ..providers.gmail.thread_provider import gmail_get_thread_full
from ..providers.imap import get_pool
from ..providers.imap.mime_analyzer import has_attachments_from_bodystructure
from ..providers.outlook.client_factory import get_outlook_client
from ..providers.outlook.message_provider import outlook_get_message_full
from ..serialization.message_enricher import (
    enrich_with_partner_meta,
    enrich_with_tags,
)
from ..utils.document_linker import find_linked_document
from ..repositories.attachment_repository import AttachmentRepository
from ..rendering.attachment_formatter import build_binary_attachment_dto


class OpenMessageAdapter:
    def __init__(self, env):
        self.env = env
        self._sync = env["mailbox.sync"]

    # Environment / models
    def env_user(self):
        return self.env.user

    def folder_browse(self, folder_id):
        return self.env["mailbox.folder"].browse(folder_id) if folder_id else None

    def account_browse(self, account_id):
        return (
            self.env["mailbox.account"].browse(account_id).exists()
            if account_id
            else None
        )

    def draft_browse(self, draft_id):
        return self.env["maildesk.draft"].sudo().browse(draft_id)

    def draft_exists(self, draft):
        return bool(draft and draft.exists())

    def partner_search(self, email):
        if not email:
            return self.env["res.partner"].browse(False)
        return self.env["res.partner"].search([(("email", "=ilike", email))], limit=1)

    def index_get_map(self, account_id, folder_name, uids):
        Index = self.env["maildesk.message_index"].sudo()
        recs = Index.search(
            [
                ("account_id", "=", account_id),
                ("folder", "=", folder_name),
                ("uid", "in", [str(u) for u in uids]),
            ]
        )
        out = {}
        for rec in recs:
            try:
                key = int(rec.uid)
            except Exception:
                continue
            out[key] = rec
        return out

    def index_browse(self, index_id: int):
        Index = self.env["maildesk.message_index"].sudo()
        return Index.browse(int(index_id)).exists()

    def index_search(self, domain, limit):
        Index = self.env["maildesk.message_index"].sudo()
        return Index.search(domain, limit=limit)

    def state_search(self, domain, limit):
        State = self.env["maildesk.email_state"].sudo()
        return State.search(domain, limit=limit)

    # Account / folder info
    def folder_account(self, folder):
        return folder.account_id if folder else None

    def folder_imap_name(self, folder):
        return getattr(folder, "imap_name", None) if folder else None

    def folder_name(self, folder):
        return getattr(folder, "name", None) if folder else None

    def folder_type(self, folder):
        return getattr(folder, "folder_type", None) or ""

    def draft_account(self, draft):
        return draft.account_id if draft else None

    def account_id(self, account):
        return account.id if account else 0

    def account_email(self, account):
        return account.email if account else ""

    def account_name(self, account):
        return account.name if account else ""

    def account_sender_name(self, account):
        return getattr(account, "sender_name", "") if account else ""

    def index_account(self, index_rec):
        return index_rec.account_id if index_rec else None

    def index_folder(self, index_rec):
        return index_rec.folder if index_rec else "INBOX"

    # Provider routing
    def is_gmail_account(self, account):
        return account.is_gmail if account else False

    def is_outlook_account(self, account):
        return account.is_outlook if account else False

    # Access control
    def check_account_access(self, account):
        return self._sync._check_account_access(account)

    # Gmail full message
    def gmail_build_service(self, account):
        return gmail_build_service(account)

    def gmail_get_message_full(self, service, account, folder, uid):
        return gmail_get_message_full(
            self.env, self._sync, service, account, folder, uid, gmail_get_thread_full
        )

    # Outlook full message
    def outlook_build_graph(self, account):
        return get_outlook_client(self.env, account)

    def outlook_get_message_full(self, sess, base, account, folder, uid):
        return outlook_get_message_full(
            self.env, self._sync, sess, base, account, folder, uid
        )

    # IMAP full message
    def get_pool(self, account):
        return get_pool(account)

    def decode_header_value(self, header):
        return decode_header_value(header)

    def to_datetime(self, date_val):
        return to_datetime(date_val)

    def join_addresses(self, addr_list):
        return join_addresses(addr_list, addr_to_email)

    def addr_to_email(self, addr_obj):
        return addr_to_email(addr_obj)

    def norm_msgid(self, msgid):
        return norm_msgid(msgid)

    def has_attachments_from_bodystructure(self, node):
        return has_attachments_from_bodystructure(node)

    # HTML/text processing
    def sanitize_email_html(self, html):
        return sanitize_email_html(html)

    def replace_cid_src(self, html, attachments, base_url=None):
        return replace_cid_src(html, attachments, base_url=base_url)

    def strip_html_to_text(self, html):
        return strip_html_to_text(html)

    def base_url(self) -> str:
        raw = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        ).strip()
        if not raw:
            return ""
        try:
            from urllib.parse import urlsplit

            parts = urlsplit(raw)
            if parts.scheme not in ("http", "https") or not parts.netloc:
                return ""
        except Exception:
            return ""
        return raw.rstrip("/")

    def materialize_provider_attachments(
        self,
        *,
        provider: str,
        account: Any,
        folder: Any,
        uid: str,
        attachments: List[Dict[str, Any]],
        index_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Materialize ALL provider attachments into `ir.attachment` linked to SSOT.

        Canonical output for the UI must be binary attachments served via
        standard Odoo routes (`/web/content`, `/web/image`) with `access_token`.
        """
        provider = (provider or "").strip().lower()
        if provider not in ("gmail", "outlook"):
            return attachments or []

        if not attachments:
            return []

        try:
            idx = int(index_id or 0)
        except Exception:
            idx = 0
        if idx <= 0:
            return attachments or []

        # Normalize to canonical index_id for Gmail/Outlook dedup across folders.
        Cache = self.env["maildesk.ui_cache"].sudo()
        idx = int(Cache.resolve_canonical_index_id(idx) or idx)

        repo = AttachmentRepository(self.env)

        def _already_materialized(att: Dict[str, Any]) -> bool:
            return bool(att.get("access_token")) and isinstance(att.get("id"), int)

        def _cid(att: Dict[str, Any]) -> str:
            raw = att.get("content_id") or att.get("contentId") or att.get("cid") or ""
            return (raw or "").strip().strip("<>").strip()

        gmail_service = None
        outlook_sess = None
        outlook_base = None

        # Build materialization requests (with bytes) for everything not already binary.
        from ...application.services.attachment_cache_service import (
            AttachmentCacheService,
            AttachmentMaterializeRequest,
            AttachmentSource,
        )

        requests: List[AttachmentMaterializeRequest] = []
        for att in attachments:
            if not isinstance(att, dict) or _already_materialized(att):
                continue

            prov_mid = (
                att.get("provider_message_id") or att.get("message_id") or uid
            ) or ""
            prov_aid = (
                att.get("provider_attachment_id")
                or att.get("attachment_id")
                or att.get("provider_id")
                or ""
            )
            prov_mid = str(prov_mid).strip()
            prov_aid = str(prov_aid).strip()
            if not prov_mid or not prov_aid:
                continue

            name = (att.get("name") or att.get("filename") or "attachment").strip()
            mimetype = (att.get("mimetype") or "application/octet-stream").strip()
            cid_val = _cid(att) or None

            data = b""
            if provider == "gmail":
                try:
                    if gmail_service is None:
                        gmail_service = self.gmail_build_service(account)
                    fetched = (
                        gmail_service.users()
                        .messages()
                        .attachments()
                        .get(userId="me", messageId=str(prov_mid), id=str(prov_aid))
                        .execute()
                    )
                    raw_b64 = fetched.get("data") or ""
                    import base64

                    data = (
                        base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
                        if raw_b64
                        else b""
                    )
                except Exception:
                    data = b""
            else:
                try:
                    if outlook_sess is None or outlook_base is None:
                        outlook_sess, outlook_base = self.outlook_build_graph(account)
                    url = f"{outlook_base}/me/messages/{prov_mid}/attachments/{prov_aid}/$value"
                    r = outlook_sess.get(url, timeout=60)
                    r.raise_for_status()
                    data = r.content or b""
                except Exception:
                    data = b""

            if not data:
                data = (
                    "MailDesk: attachment fetch failed for provider="
                    f"{provider} message_id={prov_mid} attachment_id={prov_aid}\n"
                ).encode("utf-8")
                mimetype = "text/plain"
                if not name:
                    name = "attachment.txt"
                if not name.lower().endswith(".txt"):
                    name = f"{name}.txt"

            requests.append(
                AttachmentMaterializeRequest(
                    source=(
                        AttachmentSource.PROVIDER_GMAIL
                        if provider == "gmail"
                        else AttachmentSource.PROVIDER_OUTLOOK
                    ),
                    name=name,
                    mimetype=mimetype,
                    size=len(data or b""),
                    account_id=int(getattr(account, "id", 0) or 0),
                    content_id=cid_val,
                    provider_attachment_id=prov_aid,
                    provider_message_id=prov_mid,
                    provider_url=None,
                    attachment_data=data,
                )
            )

        if not requests:
            return attachments or []

        service = AttachmentCacheService(repo)
        dtos = service.materialize_from_provider(
            requests, int(idx), force_materialize=True
        )

        out: List[Dict[str, Any]] = []
        # Preserve already-binary attachments first (for stable output on re-open).
        for att in attachments:
            if isinstance(att, dict) and _already_materialized(att):
                out.append(att)

        out.extend(
            [
                {
                    "id": dto.id,
                    "name": dto.name,
                    "filename": dto.name,
                    "mimetype": dto.mimetype,
                    "size": dto.size,
                    "type": dto.type,
                    "checksum": dto.checksum,
                    "access_token": dto.access_token,
                    "content_id": dto.content_id,
                    "contentId": dto.content_id,
                    "extension": dto.extension,
                    "icon_mimetype": dto.icon_mimetype,
                }
                for dto in dtos
            ]
        )

        return out

    def materialize_inline_attachments(
        self,
        *,
        provider: str,
        account,
        folder,
        uid: str,
        attachments,
        cache_key: int,
        needed_cids,
    ):
        """
        Materialize inline (CID) attachments into ir.attachment with access_token.

        Input `attachments` are the provider-provided attachment dicts.
        Output is the same list where matching inline attachments are replaced with
        binary attachment DTOs (id=int, access_token set, content_id preserved).
        """
        if not attachments or not needed_cids:
            return attachments or []

        Cache = self.env["maildesk.ui_cache"].sudo()
        cache_key = int(Cache.resolve_canonical_index_id(int(cache_key or 0)) or 0)
        if cache_key <= 0:
            return attachments or []

        provider = (provider or "").strip().lower()
        if provider not in ("gmail", "outlook"):
            return attachments or []

        repo = AttachmentRepository(self.env)

        def _cid(att):
            raw = att.get("content_id") or att.get("contentId") or att.get("cid") or ""
            return (raw or "").strip().strip("<>").strip()

        def _cid_matches(cid_val: str) -> bool:
            if not cid_val:
                return False
            if cid_val in needed_cids:
                return True
            if "@" in cid_val and cid_val.split("@", 1)[0] in needed_cids:
                return True
            return False

        def _already_materialized(att) -> bool:
            return bool(att.get("access_token")) and isinstance(att.get("id"), int)

        # Lazily build API clients only if we find at least one materialization candidate.
        gmail_service = None
        outlook_sess = None
        outlook_base = None
        created_by_cid: Dict[str, Dict[str, Any]] = {}

        out = []
        for att in attachments or []:
            if not isinstance(att, dict):
                out.append(att)
                continue

            cid_val = _cid(att)
            if not cid_val or not _cid_matches(cid_val) or _already_materialized(att):
                out.append(att)
                continue

            cached = created_by_cid.get(cid_val) or created_by_cid.get(
                cid_val.split("@", 1)[0] if "@" in cid_val else ""
            )
            if cached:
                out.append(cached)
                continue

            prov_mid = att.get("provider_message_id") or att.get("message_id")
            prov_aid = att.get("provider_attachment_id") or att.get("attachment_id")

            if not prov_mid or not prov_aid:
                out.append(att)
                continue

            name = att.get("name") or att.get("filename") or "inline"
            mimetype = att.get("mimetype") or "application/octet-stream"

            data = b""
            try:
                if provider == "gmail":
                    if gmail_service is None:
                        gmail_service = self.gmail_build_service(account)
                    fetched = (
                        gmail_service.users()
                        .messages()
                        .attachments()
                        .get(userId="me", messageId=str(prov_mid), id=str(prov_aid))
                        .execute()
                    )
                    raw_b64 = fetched.get("data") or ""
                    import base64

                    data = (
                        base64.urlsafe_b64decode(raw_b64.encode("utf-8"))
                        if raw_b64
                        else b""
                    )
                else:
                    if outlook_sess is None or outlook_base is None:
                        outlook_sess, outlook_base = self.outlook_build_graph(account)
                    url = f"{outlook_base}/me/messages/{prov_mid}/attachments/{prov_aid}/$value"
                    r = outlook_sess.get(url, timeout=60)
                    r.raise_for_status()
                    data = r.content or b""
            except Exception:
                data = b""

            if not data:
                out.append(att)
                continue

            created = repo.create_with_token(
                name=name,
                mimetype=mimetype,
                datas=data,
                res_model="maildesk.message_index",
                res_id=cache_key,
                description=cid_val,
            )
            dto = build_binary_attachment_dto(created)
            created_by_cid[cid_val] = dto
            if "@" in cid_val:
                created_by_cid[cid_val.split("@", 1)[0]] = dto
            out.append(dto)

        return out

    # Helpers
    def display_name_from_email(self, email):
        return display_name_from_email(email)

    def format_sender_display(self, name, email):
        return format_sender_display(name, email)

    def avatar_html(self, email, partner):
        return avatar_html(email, partner, display_name_from_email)

    def find_linked_document(self, message_id, in_reply_to):
        return find_linked_document(message_id, in_reply_to, self.env)

    def enrich_full_record_with_tags(self, account, rec):
        return enrich_with_tags(account, rec, self.env)

    def format_datetime(self, dt):
        if not dt:
            return ""
        try:
            dt_ctx = fields.Datetime.context_timestamp(self._sync, dt)
            return dt_ctx.strftime("%d %b %Y %H:%M")
        except Exception:
            return ""

    # Partner trust
    def enrich_partner_meta(self, rec):
        return enrich_with_partner_meta(rec, self.env)

    # PHASE 3: Cache integration with single-flight pattern
    def cache_read_no_lock(self, index_id):
        """Read body from ui_cache without acquiring lock (for double-checked pattern)."""
        Cache = self.env["maildesk.ui_cache"].sudo()
        cache_index_id = Cache.resolve_canonical_index_id(index_id)
        return Cache.fetch_body_cache(cache_index_id)

    def acquire_cache_lock(self, index_id):
        """Acquire advisory lock for single-flight pattern (serializes opens per index_id)."""
        Cache = self.env["maildesk.ui_cache"].sudo()
        Cache.acquire_cache_lock_for_index(index_id)

    def cache_write(self, index_id, body_html, body_text=None, attachments=None):
        """Write body to ui_cache with TTL. Caller must hold lock."""
        Cache = self.env["maildesk.ui_cache"].sudo()
        cache_index_id = Cache.resolve_canonical_index_id(index_id)
        return Cache.upsert_body_cache(
            index_id=cache_index_id,
            body_html=body_html,
            body_text=body_text,
            attachments=attachments,
        )
