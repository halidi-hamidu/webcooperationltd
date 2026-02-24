# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Open Message.

Implements the application-level use case for Open Message.
Layer: application.
"""

import logging
import re
from dataclasses import asdict, dataclass
from email import message_from_bytes, policy
from html import escape as html_escape
from typing import Any, Dict, List, Optional, Protocol, Tuple

from bs4 import BeautifulSoup

from ..errors import MailDeskInvariantError, MailDeskProviderFetchError
from ...application.services.sender_identity import SenderIdentityService
from ...application.services.attachment_cache_service import AttachmentCacheService
from ...application.services.message_display_normalizer import (
    NormalizedBody,
    _absolutize_web_image_routes,
    _scrub_remaining_cid_references,
    normalize_for_ui_cache,
)
from ...infrastructure.repositories.attachment_repository import AttachmentRepository

_logger = logging.getLogger(__name__)


class OpenMessageDeps(Protocol):
    """
    Dependency surface required to run the legacy-equivalent message open logic.

    This is a Phase A (structural) port: it intentionally mirrors the current
    mailbox_sync.get_message_with_attachments behaviors and helper calls.
    """

    # Environment / models
    def env_user(self) -> Any: ...
    def folder_browse(self, folder_id: Optional[int]) -> Any: ...
    def account_browse(self, account_id: Optional[int]) -> Any: ...
    def draft_browse(self, draft_id: int) -> Any: ...
    def draft_exists(self, draft: Any) -> bool: ...
    def partner_search(self, email: str) -> Any: ...
    def index_get_map(
        self, account_id: int, folder_name: str, uids: List[int]
    ) -> Dict[int, Any]: ...
    def index_browse(self, index_id: int) -> Any: ...
    def index_search(self, domain: List[Any], limit: int) -> Any: ...
    def state_search(self, domain: List[Any], limit: int) -> Any: ...

    # Account / folder info
    def folder_account(self, folder: Any) -> Any: ...
    def folder_imap_name(self, folder: Any) -> Optional[str]: ...
    def folder_name(self, folder: Any) -> Optional[str]: ...
    def draft_account(self, draft: Any) -> Any: ...
    def account_id(self, account: Any) -> int: ...
    def account_email(self, account: Any) -> str: ...
    def account_name(self, account: Any) -> str: ...
    def account_sender_name(self, account: Any) -> str: ...
    def index_account(self, index_rec: Any) -> Any: ...
    def index_folder(self, index_rec: Any) -> str: ...

    # Provider routing
    def is_gmail_account(self, account: Any) -> bool: ...
    def is_outlook_account(self, account: Any) -> bool: ...

    # Access control
    def check_account_access(self, account: Any) -> None: ...

    # Gmail full message
    def gmail_build_service(self, account: Any) -> Any: ...
    def gmail_get_message_full(
        self, service: Any, account: Any, folder: Any, uid: str
    ) -> Dict[str, Any]: ...

    # Outlook full message
    def outlook_build_graph(self, account: Any) -> Tuple[Any, Any]: ...
    def outlook_get_message_full(
        self, sess: Any, base: Any, account: Any, folder: Any, uid: str
    ) -> Dict[str, Any]: ...

    # IMAP full message
    def get_pool(self, account: Any) -> Any: ...
    def decode_header_value(self, header: Any) -> str: ...
    def to_datetime(self, date_val: Any) -> Any: ...
    def join_addresses(self, addr_list: Any) -> str: ...
    def addr_to_email(self, addr_obj: Any) -> str: ...
    def norm_msgid(self, msgid: str) -> str: ...
    def has_attachments_from_bodystructure(self, node: Any) -> bool: ...

    # HTML/text processing
    def sanitize_email_html(self, html: str) -> str: ...
    def replace_cid_src(
        self,
        html: str,
        attachments: List[Dict[str, Any]],
        base_url: Optional[str] = None,
    ) -> str: ...
    def strip_html_to_text(self, html: str) -> str: ...
    def base_url(self) -> str: ...
    def materialize_inline_attachments(
        self,
        *,
        provider: str,
        account: Any,
        folder: Any,
        uid: str,
        attachments: List[Dict[str, Any]],
        cache_key: int,
        needed_cids: set[str],
    ) -> List[Dict[str, Any]]: ...

    def materialize_provider_attachments(
        self,
        *,
        provider: str,
        account: Any,
        folder: Any,
        uid: str,
        attachments: List[Dict[str, Any]],
        index_id: int,
    ) -> List[Dict[str, Any]]: ...

    # Helpers
    def display_name_from_email(self, email: str) -> str: ...
    def format_sender_display(self, name: str, email: str) -> str: ...
    def avatar_html(self, email: str, partner: Any) -> str: ...
    def find_linked_document(
        self, message_id: Optional[str], in_reply_to: Optional[str]
    ) -> Tuple[Any, Any]: ...
    def enrich_full_record_with_tags(
        self, account: Any, rec: Dict[str, Any]
    ) -> Dict[str, Any]: ...
    def format_datetime(self, dt: Any) -> str: ...

    # Partner trust
    def enrich_partner_meta(self, rec: Dict[str, Any]) -> Dict[str, Any]: ...

    # Cache integration (PHASE 3)
    def cache_read(self, index_id: int) -> Optional[Dict[str, Any]]: ...
    def cache_write(
        self,
        index_id: int,
        body_html: str,
        body_text: Optional[str] = None,
        attachments: Optional[List] = None,
    ) -> Any: ...


@dataclass(frozen=True)
class OpenMessageParams:
    """Parameters for opening a message."""

    uid: Any
    index_id: Optional[int] = None
    folder_id: Optional[int] = None
    account_id: Optional[int] = None
    is_internal_draft: bool = False


class OpenMessage:
    """
    Phase A use-case: mechanical extraction of mailbox_sync.get_message_with_attachments.

    Not wired yet. Must preserve behavior and DTO shape 1:1 with the legacy
    implementation.
    """

    def __init__(self, deps: OpenMessageDeps):
        self._deps = deps
        self._sender_service = SenderIdentityService(deps)

    def _fetch_provider_payload(
        self, *, index_rec: Any, account: Any, folder: Any
    ) -> Dict[str, Any]:
        provider_name = (getattr(index_rec, "provider", None) or "").strip().lower()

        if provider_name == "gmail":
            provider_response = self._open_gmail_message(
                account,
                folder,
                getattr(index_rec, "uid", None),
                message_id=getattr(index_rec, "message_id", None),
            )
        elif provider_name == "outlook":
            provider_response = self._open_outlook_message(
                account,
                folder,
                getattr(index_rec, "uid", None),
            )
        else:
            folder_name = getattr(index_rec, "folder", None) or "INBOX"
            provider_response = self._open_imap_message(
                account,
                folder_name,
                getattr(index_rec, "uid", None),
                message_id=getattr(index_rec, "message_id", None),
                fallback_folder=getattr(index_rec, "pending_move_to", None),
            )

        if not provider_response:
            raise MailDeskProviderFetchError(
                f"Provider fetch returned empty for provider={provider_name or 'unknown'} index_id={getattr(index_rec, 'id', None)} uid={getattr(index_rec, 'uid', None)!r}"
            )

        return {
            "body_html": provider_response.get("body_html")
            or provider_response.get("body_original"),
            "body_text": provider_response.get("body_text")
            or provider_response.get("body_plain"),
            "attachments": provider_response.get("attachments") or [],
            "provider": provider_name,
            "has_attachments": provider_response.get("has_attachments"),
        }

    def _ensure_body_cached(
        self,
        *,
        index_rec: Any,
        account: Any,
        folder: Any,
        provider_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Single-flight cache hydration for message body.

        - Cache-first (double-checked)
        - Acquire advisory lock BEFORE provider fetch
        - Normalize once, write once
        """
        if getattr(index_rec, "local_pending", False):
            cached = self._deps.cache_read_no_lock(index_rec.id)
            if cached is None:
                raise MailDeskInvariantError(
                    "Local-pending message without cache is not openable"
                )
            return cached

        cached = self._deps.cache_read_no_lock(index_rec.id)
        if cached is not None:
            return cached

        self._deps.acquire_cache_lock(index_rec.id)
        cached = self._deps.cache_read_no_lock(index_rec.id)
        if cached is not None:
            return cached

        payload = provider_payload or self._fetch_provider_payload(
            index_rec=index_rec, account=account, folder=folder
        )

        raw_html = payload.get("body_html") or payload.get("body_original") or ""
        raw_text = payload.get("body_text") or payload.get("body_plain") or ""
        attachments = payload.get("attachments") or []
        provider_name = (
            payload.get("provider")
            or (getattr(index_rec, "provider", None) or "").strip().lower()
        )

        if provider_name in ("gmail", "outlook") and attachments:
            try:
                attachments = self._deps.materialize_provider_attachments(
                    provider=provider_name,
                    account=account,
                    folder=folder,
                    uid=str(getattr(index_rec, "uid", "") or ""),
                    attachments=list(attachments or []),
                    index_id=int(index_rec.id),
                )
                payload["attachments"] = attachments
            except Exception:
                _logger.exception(
                    "[OpenMessage] Provider attachment materialization failed (provider=%s index_id=%s uid=%r)",
                    provider_name,
                    getattr(index_rec, "id", None),
                    getattr(index_rec, "uid", None),
                )

        try:
            normalized = normalize_for_ui_cache(
                self._deps,
                provider=provider_name,
                account=account,
                folder=folder,
                uid=str(getattr(index_rec, "uid", "")),
                cache_key=int(index_rec.id),
                body_html=raw_html,
                body_text=raw_text,
                attachments=attachments,
            )
        except Exception as e:
            _logger.error(
                "[OpenMessage] Normalize failed; caching scrubbed body (index_id=%s provider=%s uid=%r): %s",
                getattr(index_rec, "id", None),
                provider_name,
                getattr(index_rec, "uid", None),
                e,
                exc_info=True,
            )
            fallback_html = self._deps.sanitize_email_html(raw_html or "")
            fallback_html, _ = _scrub_remaining_cid_references(fallback_html or "")
            if "cid:" in (fallback_html or "").lower():
                fallback_html = re.sub(
                    r"(?i)url\(\s*cid:[^)]+\)",
                    "",
                    fallback_html or "",
                )
                fallback_html = re.sub(
                    r"cid:[^\s\"'>]+",
                    "",
                    fallback_html or "",
                    flags=re.IGNORECASE,
                )
            if "about:blank" in (fallback_html or "").lower():
                fallback_html = (fallback_html or "").replace("about:blank", "")

            base_url = (self._deps.base_url() or "").strip() or "http://invalid.local"
            fallback_html = _absolutize_web_image_routes(fallback_html or "", base_url)
            normalized = NormalizedBody(
                body_html=fallback_html or "",
                body_text=raw_text
                or self._deps.strip_html_to_text(fallback_html)
                or "",
                attachments=attachments,
            )

        cache_payload = {
            "body_html": normalized.body_html,
            "body_text": normalized.body_text,
            "attachments": normalized.attachments,
            "has_attachments": payload.get("has_attachments"),
        }

        _logger.info(
            f"[OpenMessage] Writing fetched data to cache for index_id={getattr(index_rec, 'id', None)}"
        )
        self._deps.cache_write(
            index_id=index_rec.id,
            body_html=cache_payload["body_html"],
            body_text=cache_payload["body_text"],
            attachments=cache_payload["attachments"],
        )
        return cache_payload

    def execute(self, params: OpenMessageParams) -> Dict[str, Any]:
        """
        Open a message and return its full details including body and attachments.

        CACHE INTEGRATION:
        1. Try cache first (read-through)
        2. On miss, fetch from provider
        3. Write to cache after fetch
        """
        _logger.info(
            f"==== [OpenMessage START] uid={params.uid}, folder_id={params.folder_id}, account_id={params.account_id} ===="
        )

        if params.is_internal_draft:
            _logger.info("[OpenMessage] Processing as INTERNAL DRAFT")
            return self._open_internal_draft(params)

        # Resolve SSOT index record (required for deterministic cache behavior).
        # Invariants:
        # - We never guess "UID vs DB id" by numeric shape (IMAP UIDs are numeric too).
        # - We must have a message_index row to key ui_cache.
        uid = params.uid
        index_rec = None
        folder = None
        account = None
        folder_name = None

        if params.index_id:
            index_rec = self._deps.index_browse(int(params.index_id))
            if not index_rec or not getattr(index_rec, "id", None):
                raise MailDeskInvariantError(
                    f"OpenMessage requires valid SSOT index_id; got {params.index_id!r}"
                )
            account = self._deps.index_account(index_rec)
            folder_name = self._deps.index_folder(index_rec) or "INBOX"
            uid = getattr(index_rec, "uid", uid)
            folder = (
                self._deps.folder_browse(params.folder_id) if params.folder_id else None
            )
            _logger.info(
                f"[OpenMessage] Resolved via index_id: index_id={index_rec.id}, folder={folder_name}, account={account.id}"
            )
        elif params.folder_id:
            folder = self._deps.folder_browse(params.folder_id)
            if not folder:
                raise MailDeskInvariantError(
                    f"OpenMessage folder_id {params.folder_id!r} not found"
                )
            account = self._deps.folder_account(folder)
            folder_name = self._deps.folder_imap_name(folder) or self._deps.folder_name(
                folder
            )
            if not account:
                raise MailDeskInvariantError(
                    f"OpenMessage could not resolve account for folder_id={params.folder_id!r}"
                )
            index_match = self._deps.index_search(
                [
                    ("account_id", "=", account.id),
                    ("folder", "=", folder_name),
                    ("uid", "=", str(uid)),
                ],
                limit=2,
            )
            if not index_match:
                raise MailDeskInvariantError(
                    f"SSOT index missing for account_id={account.id} folder={folder_name!r} uid={uid!r}"
                )
            if len(index_match) > 1:
                raise MailDeskInvariantError(
                    f"SSOT index not unique for account_id={account.id} folder={folder_name!r} uid={uid!r}"
                )
            index_rec = index_match[0]
            _logger.info(
                f"[OpenMessage] Resolved via folder_id: index_id={index_rec.id}, folder={folder_name}, account={account.id}"
            )
        else:
            if not params.account_id:
                raise MailDeskInvariantError(
                    "OpenMessage requires either index_id, or folder_id, or account_id+uid"
                )
            account = self._deps.account_browse(params.account_id)
            if not account:
                raise MailDeskInvariantError(
                    f"OpenMessage account_id {params.account_id!r} not found"
                )
            index_match = self._deps.index_search(
                [("account_id", "=", account.id), ("uid", "=", str(uid))], limit=2
            )
            if not index_match:
                raise MailDeskInvariantError(
                    f"SSOT index missing for account_id={account.id} uid={uid!r}; provide folder_id or index_id"
                )
            if len(index_match) > 1:
                raise MailDeskInvariantError(
                    f"SSOT index ambiguous for account_id={account.id} uid={uid!r}; provide folder_id or index_id"
                )
            index_rec = index_match[0]
            folder_name = self._deps.index_folder(index_rec) or "INBOX"
            _logger.info(
                f"[OpenMessage] Resolved via account_id+uid: index_id={index_rec.id}, folder={folder_name}, account={account.id}"
            )

        self._deps.check_account_access(account)

        cache_payload = self._ensure_body_cached(
            index_rec=index_rec, account=account, folder=folder
        )

        provider_has_atts = cache_payload.get("has_attachments")
        if provider_has_atts is None:
            provider_has_atts = bool(cache_payload.get("attachments"))
        if index_rec.has_attachments != provider_has_atts:
            index_rec.write({"has_attachments": provider_has_atts})
            _logger.info(
                f"[OpenMessage] Updated has_attachments: {index_rec.has_attachments} → {provider_has_atts}"
            )

        _logger.info("[OpenMessage] Returning response with cached data")
        return self._build_response_from_cache(
            index_rec, cache_payload, account, folder
        )

    def _build_response_from_cache(
        self, index_rec: Any, cached: Dict[str, Any], account: Any, folder: Any
    ) -> Dict[str, Any]:
        """
        Build response DTO from cache + SSOT.

        CRITICAL: Metadata from SSOT (message_index), body from cache.
        SENT FOLDER: Show recipient instead of sender.
        """
        # CANONICAL SENDER RESOLUTION
        identity = self._sender_service.resolve_visual_identity(
            from_addr=index_rec.from_addr or "",
            to_addrs=index_rec.to_addrs or "",
            sender_display_name_header=index_rec.sender_display_name,
            folder=folder,
            folder_name_heuristic=index_rec.folder,
        )

        # Base DTO from SSOT
        dto = {
            "id": index_rec.id,  # SSOT Database ID
            "uid": index_rec.uid,
            "subject": index_rec.subject or "(No Subject)",
            "email_from": identity["visual_email"],  # UI Compatibility Alias (Visual)
            "from_addr": index_rec.from_addr or "",  # Technical Sender (Immutable SSOT)
            "visual_email": identity["visual_email"],  # Explicit Visual Email
            "sender_display_name": identity["sender_display_name"],  # Visual Name
            "to_addrs": index_rec.to_addrs or "",
            "cc_addrs": index_rec.cc_addrs or "",
            "date": index_rec.date,
            "formatted_date": self._deps.format_datetime(index_rec.date)
            if index_rec.date
            else "",
            "message_id": index_rec.message_id or "",
            "message_id_norm": index_rec.message_id or "",
            "in_reply_to": index_rec.in_reply_to or "",
            "references_hdr": index_rec.references_hdr or "",
            "thread_id": index_rec.thread_id or "",
            "sort_ts": index_rec.sort_ts or 0,
            "is_read": index_rec.is_read,
            "is_starred": index_rec.is_starred,
            "flags": index_rec.flags or "",
            "has_attachments": index_rec.has_attachments,
            "backend_type": index_rec.provider or "imap",
            "account_id": [account.id, account.name] if account else False,
            "folder_id": folder.id if folder else False,
            "folder_name": index_rec.folder,
            "folder_type": identity["folder_type"],
            "avatar_html": identity["avatar_html"],
            "avatar_partner_id": identity["avatar_partner_id"],
            "partner_trusted": identity["partner_trusted"],
            "content_trusted": identity["content_trusted"],
            "trusted_by_user_id": identity["trusted_by_user_id"],
        }

        # Body from cache (UI artifact)
        body_html = cached.get("body_html")
        if body_html is None:
            _logger.error(
                "[OpenMessage] ui_cache missing body_html (index_id=%s); returning empty body",
                getattr(index_rec, "id", None),
            )
            body_html = ""
        dto["body_html"] = body_html or ""
        dto["body_original"] = body_html or ""
        dto["body_text"] = cached.get("body_text") or ""
        dto["attachments"] = cached.get("attachments") or []

        # Enrich with partner/tags
        dto = self._deps.enrich_full_record_with_tags(account, dto)
        # Note: enrich_partner_meta usually recalculates trust, but our service did it.
        # But we keep it if it adds other meta.
        dto = self._deps.enrich_partner_meta(dto)

        # Linked document
        m, r = self._deps.find_linked_document(
            dto.get("message_id_norm"), dto.get("in_reply_to")
        )
        dto["model"] = m
        dto["res_id"] = r

        return dto

    def _apply_sent_folder_display(
        self, rec: Dict[str, Any], folder: Any
    ) -> Dict[str, Any]:
        """
        Apply sent folder display logic to provider response.
        Uses Canonical Sender Service.
        """
        if not rec:
            return rec

        # Use canonical service
        identity = self._sender_service.resolve_visual_identity(
            from_addr=rec.get("email_from") or rec.get("from_addr") or "",
            to_addrs=rec.get("to_addrs") or rec.get("to_display") or "",
            sender_display_name_header=rec.get("sender_display_name"),
            folder=folder,
            folder_name_heuristic=None,  # Provider fetch might not know heuristic unless we pass it
        )

        rec["sender_display_name"] = identity["sender_display_name"]
        rec["avatar_html"] = identity["avatar_html"]
        rec["avatar_partner_id"] = identity["avatar_partner_id"]
        rec["partner_trusted"] = identity["partner_trusted"]
        rec["content_trusted"] = identity["content_trusted"]
        rec["trusted_by_user_id"] = identity["trusted_by_user_id"]
        # visual_email not usually in provider payload, but we can add it if needed

        return rec

    def _open_internal_draft(self, params: OpenMessageParams) -> Dict[str, Any]:
        """Open an internal draft (maildesk.draft)."""
        try:
            draft_id = int(params.uid)
        except Exception:
            return {}

        draft = self._deps.draft_browse(draft_id)
        if not self._deps.draft_exists(draft):
            return {}

        account = self._deps.draft_account(draft)
        self._deps.check_account_access(account)

        email_from_val = (self._deps.account_email(account) or "").lower()
        partner = self._deps.partner_search(email_from_val)

        # Build DTO for draft
        res = self._build_draft_dto(draft, account, email_from_val, partner)

        # Preserve folder context and msg_key so the frontend can keep selection
        # stable (especially across refreshes).
        if params.folder_id:
            res["folder_id"] = int(params.folder_id)
            res["msg_key"] = (
                f"{self._deps.account_id(account)}|{int(params.folder_id)}|draft|{draft_id}"
            )

        # Provide uid for uniform UI handling (draft id in draft-space).
        res.setdefault("uid", str(draft_id))
        return res

    def _build_draft_dto(
        self, draft: Any, account: Any, email_from: str, partner: Any
    ) -> Dict[str, Any]:
        """Build DTO for internal draft."""

        dt = getattr(draft, "write_date", None) or getattr(draft, "create_date", None)
        formatted_date = self._deps.format_datetime(dt) if dt else ""

        # Extract body_plain
        body_html_val = getattr(draft, "body_html", None) or ""
        try:
            body_plain = ""
            if body_html_val:
                try:
                    body_plain = BeautifulSoup(body_html_val, "lxml").get_text(
                        "\n", strip=True
                    )
                except Exception:
                    body_plain = BeautifulSoup(body_html_val, "html.parser").get_text(
                        "\n", strip=True
                    )
        except Exception:
            body_plain = body_html_val[:1024]

        # Build attachments using AttachmentCacheService
        # Service ensures tokens and builds pure DTOs
        attachment_ids = [
            getattr(a, "id", 0) for a in getattr(draft, "attachment_ids", [])
        ]
        attachments_json = []
        if attachment_ids:
            repo = AttachmentRepository(self._deps.env_user())
            service = AttachmentCacheService(repo)
            dtos = service.materialize_for_draft(attachment_ids)
            attachments_json = [asdict(d) for d in dtos]

        account_name = self._deps.account_name(account)
        account_email_val = self._deps.account_email(account)

        res = {
            "id": getattr(draft, "id", 0),
            "subject": getattr(draft, "subject", None) or "",
            "email_from": email_from,
            "date": dt,
            "formatted_date": formatted_date,
            "body_original": self._deps.sanitize_email_html(body_html_val),
            "body_html": self._deps.sanitize_email_html(
                self._deps.replace_cid_src(body_html_val, attachments_json)
            ),
            "body_plain": body_plain or "",
            "is_read": False,
            "is_starred": False,
            "has_attachments": bool(attachments_json),
            "attachments": attachments_json,
            "account_display": (
                f"{account_name} | {account_email_val}"
                if account_name != account_email_val
                else (account_email_val or "")
            ),
            "to_display": getattr(draft, "to_emails", None) or "",
            "cc_display": getattr(draft, "cc_emails", None) or "",
            "bcc_display": getattr(draft, "bcc_emails", None) or "",
            "account_id": [self._deps.account_id(account), account_name],
            "model": getattr(draft, "model", None) or False,
            "res_id": getattr(draft, "res_id", None) or False,
            "is_draft": True,
            "is_local_draft": True,
            "folder_type": "drafts",
            "content_trusted": True,
            "tag_ids": [
                {"id": t.id, "name": t.name, "color": t.color} for t in draft.tag_ids
            ],
            "sender_display_name": (
                getattr(draft, "sender_display_name", None)
                or self._deps.format_sender_display(
                    self._deps.account_sender_name(account) or account_name,
                    email_from,
                )
            ),
            "in_reply_to": getattr(draft, "reply_to_message_id", None) or "",
            "message_id": getattr(draft, "message_id", None) or "",
            "parent_chain": False,
        }
        # Enrich with partner metadata (tags already populated from draft)
        return self._deps.enrich_partner_meta(res)

    def _open_gmail_message(
        self, account: Any, folder: Any, uid: Any, *, message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Open Gmail message via API."""
        service = self._deps.gmail_build_service(account)
        rec = (
            self._deps.gmail_get_message_full(service, account, folder, str(uid)) or {}
        )
        if rec and "backend_type" not in rec:
            rec["backend_type"] = "gmail"
        if rec and "folder_id" not in rec:
            rec["folder_id"] = getattr(folder, "id", None) if folder else False

        # SENT FOLDER LOGIC: Apply display contact transformation
        rec = self._apply_sent_folder_display(rec, folder)

        # Enrich partner trust info
        rec = self._deps.enrich_partner_meta(rec)

        # Normalize message_id
        if "message_id_norm" not in rec and rec.get("message_id"):
            rec["message_id_norm"] = rec["message_id"]

        # Process body HTML
        raw_body = rec.get("body_original") or rec.get("body_html") or ""

        # CID resolution + sanitization happen centrally in `message_display_normalizer` before caching.
        rec["body_original"] = raw_body
        rec["body_html"] = raw_body

        # Find linked document
        m, r = self._deps.find_linked_document(
            rec.get("message_id_norm"), rec.get("in_reply_to")
        )
        rec["model"] = m
        rec["res_id"] = r

        return self._deps.enrich_full_record_with_tags(account, rec)

    def _open_outlook_message(
        self, account: Any, folder: Any, uid: Any
    ) -> Dict[str, Any]:
        """Open Outlook message via Graph API."""

        sess, base = self._deps.outlook_build_graph(account)

        # Outlook UIDs must not be purely numeric (Graph IDs are opaque strings)
        if re.fullmatch(r"\d+", str(uid)):
            raise MailDeskProviderFetchError(
                f"Outlook message uid is invalid (numeric): {uid!r}"
            )

        rec = (
            self._deps.outlook_get_message_full(sess, base, account, folder, str(uid))
            or {}
        )

        # SENT FOLDER LOGIC: Apply display contact transformation
        rec = self._apply_sent_folder_display(rec, folder)

        # Enrich partner trust info
        rec = self._deps.enrich_partner_meta(rec)

        # Normalize message_id
        if "message_id_norm" not in rec and rec.get("message_id"):
            rec["message_id_norm"] = rec["message_id"]

        # Process body HTML
        raw_body = rec.get("body_original") or rec.get("body_html") or ""

        # CID resolution + sanitization happen centrally in `message_display_normalizer` before caching.
        rec["body_original"] = raw_body
        rec["body_html"] = raw_body

        # Find linked document
        m, r = self._deps.find_linked_document(
            rec.get("message_id_norm"), rec.get("in_reply_to")
        )
        rec["model"] = m
        rec["res_id"] = r

        return self._deps.enrich_full_record_with_tags(account, rec)

    def _open_imap_message(
        self,
        account: Any,
        folder_name: str,
        uid: Any,
        message_id: str = None,
        fallback_folder: str = None,
    ) -> Dict[str, Any]:
        """Open IMAP message by fetching full RFC822 and parsing.
        Supports recovery by Message-ID if UID fetch fails."""

        # IMAP UID must be numeric
        if not re.fullmatch(r"\d+", str(uid or "")):
            _logger.error(
                f"[OpenMessage] [IMAP] Aborting fetch: non-numeric UID '{uid}' for provider=imap"
            )
            raise MailDeskProviderFetchError(
                f"IMAP message uid is invalid (non-numeric): {uid!r}"
            )

        uid_int = int(uid)
        pool = self._deps.get_pool(account)
        returned = None

        # Helper to try fetch from specific folder and UID
        def try_fetch(client_sess, f_name, uids_list):
            if not self._safe_select_imap(client_sess, f_name):
                _logger.warning(
                    f"[OpenMessage] [IMAP] Failed to select folder '{f_name}' during fetch"
                )
                return {}, {}, []

            fetch_keys = [
                "ENVELOPE",
                "FLAGS",
                "UID",
                "BODYSTRUCTURE",
                "RFC822.SIZE",
                "INTERNALDATE",
            ]
            try:
                _logger.info(
                    f"[OpenMessage] [IMAP] Fetching UIDs {uids_list} from folder '{f_name}'"
                )
                hd_res = client_sess.fetch(uids_list, fetch_keys) or {}
                _logger.info(
                    f"[OpenMessage] [IMAP] Header fetch returned {len(hd_res)} results"
                )

                # If header fetch succeeded, try body
                if not hd_res:
                    _logger.warning(
                        f"[OpenMessage] [IMAP] Header fetch returned EMPTY for UIDs {uids_list} in '{f_name}'"
                    )
                    return {}, {}, []

                _logger.info(f"[OpenMessage] [IMAP] Fetching BODY for UIDs {uids_list}")
                fd_res = client_sess.fetch(uids_list, ["BODY.PEEK[]"]) or {}
                _logger.info(
                    f"[OpenMessage] [IMAP] Body fetch returned {len(fd_res)} results"
                )

                if not fd_res:
                    _logger.warning(
                        f"[OpenMessage] [IMAP] Body fetch returned EMPTY for UIDs {uids_list} in '{f_name}'"
                    )

                return hd_res, fd_res, uids_list
            except Exception as fetch_err:
                _logger.error(
                    f"[OpenMessage] [IMAP] Fetch exception for UIDs {uids_list} in '{f_name}': {fetch_err}",
                    exc_info=True,
                )
                return {}, {}, []

        try:
            with pool.session() as client:
                # 1. Primary Attempt: Fetch by UID in current folder
                found_hd = {}
                found_fd = {}
                found_uid = 0

                # attempt 1
                found_hd, found_fd, _ = try_fetch(client, folder_name, [uid_int])

                if found_hd:
                    found_uid = uid_int

                # 2. Recovery: If failed and message_id is known, search in current folder
                if not found_hd and message_id:
                    # Search by Message-ID
                    if self._safe_select_imap(client, folder_name):
                        try:
                            clean_mid = message_id.strip()
                            if not clean_mid.startswith("<"):
                                clean_mid = f"<{clean_mid}>"

                            found_uids = client.search(
                                ["HEADER", "Message-ID", clean_mid]
                            )
                            if found_uids:
                                # Found it! It has a new UID.
                                new_uid = found_uids[0]
                                found_hd, found_fd, _ = try_fetch(
                                    client, folder_name, [new_uid]
                                )
                                if found_hd:
                                    found_uid = new_uid
                        except Exception:
                            pass

                # 3. Fallback: If still not found and fallback_folder exists, try there
                if (
                    not found_hd
                    and message_id
                    and fallback_folder
                    and fallback_folder != folder_name
                ):
                    if self._safe_select_imap(client, fallback_folder):
                        try:
                            clean_mid = message_id.strip()
                            if not clean_mid.startswith("<"):
                                clean_mid = f"<{clean_mid}>"

                            found_uids = client.search(
                                ["HEADER", "Message-ID", clean_mid]
                            )
                            if found_uids:
                                new_uid = found_uids[0]
                                found_hd, found_fd, _ = try_fetch(
                                    client, fallback_folder, [new_uid]
                                )
                                if found_hd:
                                    found_uid = new_uid
                                    folder_name = fallback_folder  # Update context for subsequent processing
                        except Exception:
                            pass

                # If we have data, process it
                if found_hd and found_fd and found_uid:
                    # Get SSOT index map
                    index_map = {}
                    try:
                        index_map = self._deps.index_get_map(
                            self._deps.account_id(account), folder_name, [found_uid]
                        )
                    except Exception:
                        pass

                    hd = found_hd.get(found_uid, {}) or {}
                    fd = found_fd.get(found_uid, {}) or {}
                    blob = fd.get(b"BODY[]", b"")

                    if blob:
                        returned = self._process_imap_message(
                            blob,
                            hd,
                            found_uid,
                            account,
                            folder_name,
                            index_map.get(found_uid),
                        )
                    else:
                        _logger.error(
                            f"[OpenMessage] IMAP fetch succeeded but BODY[] is empty! uid={found_uid} folder={folder_name}"
                        )
                else:
                    _logger.error(
                        f"[OpenMessage] IMAP fetch failed: "
                        f"found_hd={bool(found_hd)} found_fd={bool(found_fd)} found_uid={found_uid} "
                        f"requested_uid={uid_int} folder={folder_name}"
                    )

        except Exception as e:
            _logger.error(f"[OpenMessage] IMAP fetch exception: {e}", exc_info=True)
            raise MailDeskProviderFetchError(
                f"IMAP fetch exception for uid={uid!r} folder={folder_name!r}: {e}"
            ) from e

        if not returned:
            _logger.error(
                f"[OpenMessage] IMAP returned None after all attempts. uid={uid} folder={folder_name}"
            )
            raise MailDeskProviderFetchError(
                f"IMAP returned empty after all attempts for uid={uid!r} folder={folder_name!r}"
            )

        # Apply state overlays
        returned = self._apply_imap_state_overlays(
            account, folder_name, str(uid), returned
        )

        # SENT FOLDER LOGIC: Apply display contact transformation
        # For IMAP, we need to find folder record to get folder_type
        folder_rec = (
            self._deps.env_user()
            .env["mailbox.folder"]
            .sudo()
            .search(
                [
                    ("account_id", "=", account.id),
                    ("name", "=", folder_name),
                ],
                limit=1,
            )
        )
        returned = self._apply_sent_folder_display(returned, folder_rec)

        # Enrich partner trust info
        returned = self._deps.enrich_partner_meta(returned)

        # Find linked document
        m, r = self._deps.find_linked_document(
            returned.get("message_id_norm"), returned.get("in_reply_to")
        )
        returned["model"] = m
        returned["res_id"] = r

        # Enrich tags (body normalization happens centrally before caching)
        returned = self._deps.enrich_full_record_with_tags(account, returned)

        return returned

    def _safe_select_imap(self, client: Any, folder_name: str) -> bool:
        """Try to select IMAP folder, with delimiter fallback."""
        try:
            client.select_folder(folder_name, readonly=True)
            return True
        except Exception:
            try:
                delim = self._get_imap_delim(client) or "/"
                alt = (folder_name or "").replace("\\", delim).replace("/", delim)
                if alt and alt != folder_name:
                    client.select_folder(alt, readonly=True)
                    return True
            except Exception:
                pass
            return False

    def _get_imap_delim(self, client: Any) -> str:
        """Get IMAP folder delimiter."""
        try:
            ns = client.namespace()
            for grp in ns or []:
                for _, d in grp or []:
                    if d:
                        return d
        except Exception:
            pass

        try:
            res = client.list_folders("", "")
            if res and len(res[0]) >= 2 and res[0][1]:
                return res[0][1]
        except Exception:
            pass

        return "/"

    def _process_imap_message(
        self,
        blob: bytes,
        header_data: Dict[Any, Any],
        uid: int,
        account: Any,
        folder_name: str,
        index_rec: Any,
    ) -> Dict[str, Any]:
        """Parse RFC822 blob and build DTO."""

        try:
            msg = message_from_bytes(blob, policy=policy.default)
        except Exception:
            return {}

        env = header_data.get(b"ENVELOPE")
        flags = header_data.get(b"FLAGS", []) or []
        bs = header_data.get(b"BODYSTRUCTURE")

        # Extract threading headers
        raw_msg_id = msg["Message-ID"] or ""
        raw_in_reply = msg["In-Reply-To"] or ""
        msg_id_norm = self._deps.norm_msgid(raw_msg_id)
        in_reply_norm = self._deps.norm_msgid(raw_in_reply)

        # Subject
        subject = (
            index_rec.subject
            if index_rec
            else self._deps.decode_header_value(msg["Subject"] or "") or "(no subject)"
        )

        # Sender email
        sender_email = self._extract_sender_email(msg, env)
        msg_date = self._deps.to_datetime(msg["Date"] or getattr(env, "date", None))

        # To/Cc/Bcc
        if index_rec:
            to_display = index_rec.to_addrs or ""
            cc_display = index_rec.cc_addrs or ""
            bcc_display = index_rec.bcc_addrs or ""
        else:
            to_display = self._deps.join_addresses(
                getattr(env, "to", None) if env else None
            )
            cc_display = self._deps.join_addresses(
                getattr(env, "cc", None) if env else None
            )
            bcc_display = self._deps.join_addresses(
                getattr(env, "bcc", None) if env else None
            )

        # Extract body
        body_html, body_plain = self._extract_imap_body(msg)

        # If only plain, convert to HTML
        if not body_html and body_plain:
            safe_plain = html_escape(body_plain)
            body_html = (
                "<p style='white-space: pre-wrap; margin:0;'>" + safe_plain + "</p>"
            )

        # Attachments flag
        has_attachments_flag = (
            index_rec.has_attachments
            if index_rec
            else self._deps.has_attachments_from_bodystructure(bs)
        )

        # Build attachment list (materialized to ir.attachment)
        # Note: We use index_rec.id as the cache link (index_rec is the message_index record)
        attachments_json = self._build_imap_attachments(
            msg, account, folder_name, uid, index_rec.id
        )
        has_attachments_real = bool(attachments_json)
        if not has_attachments_real and has_attachments_flag:
            has_attachments_real = True

        # CID resolution happens centrally in `message_display_normalizer` before caching.
        body_html_resolved = body_html

        sender_name = self._deps.display_name_from_email(sender_email)

        account_name = self._deps.account_name(account)
        account_email = self._deps.account_email(account)

        result = {
            "id": uid,
            "subject": subject,
            "email_from": (sender_email or "").lower(),
            "date": msg_date,
            "formatted_date": self._deps.format_datetime(msg_date) if msg_date else "",
            "body_original": body_html,  # RAW (with CIDs)
            "body_html": body_html_resolved,  # DISPLAY (rewritten)
            "body_plain": body_plain,
            "is_read": b"\\Seen" in flags,
            "is_starred": b"\\Flagged" in flags,
            "has_attachments": has_attachments_real,
            "attachments": attachments_json,
            "account_display": (
                f"{account_name} | {account_email}"
                if account_name != account_email
                else account_email
            ),
            "to_display": to_display or "",
            "cc_display": cc_display or "",
            "bcc_display": bcc_display or "",
            "account_id": [self._deps.account_id(account), account_name],
            "model": False,
            "res_id": False,
            "is_draft": b"\\Draft" in flags,
            "tag_ids": [],  # Will be enriched if index record exists
            "sender_display_name": self._deps.format_sender_display(
                sender_name, sender_email
            ),
            "in_reply_to": in_reply_norm,
            "message_id": msg_id_norm,
            "message_id_norm": msg_id_norm,
        }

        # Enrich with tags from message_index if available
        # This tries to retrieve tag_ids from SSOT
        try:
            result = self._deps.enrich_full_record_with_tags(account, result)
        except Exception:
            # If enrichment fails, keep empty tag_ids
            pass

        return result

    def _extract_sender_email(self, msg: Any, env: Any) -> str:
        """Extract sender email from message."""
        sender_email = ""
        from_header = msg["From"]

        if from_header and hasattr(from_header, "addresses") and from_header.addresses:
            parsed_from = from_header.addresses[0]
            sender_email = (parsed_from.addr_spec or "").lower()
        elif from_header:
            sender_email = str(from_header)

        if not sender_email and env and getattr(env, "from_", None):
            sender_email = self._deps.addr_to_email(env.from_[0])

        return sender_email

    def _extract_imap_body(self, msg: Any) -> Tuple[str, str]:
        """Extract HTML and plain text bodies from IMAP message."""
        body_html = ""
        body_plain = ""

        try:
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = (part.get_content_type() or "").lower()
                    if ctype == "text/html":
                        try:
                            body_html += part.get_content()
                        except Exception:
                            body_html += (part.get_payload(decode=True) or b"").decode(
                                "utf-8", "ignore"
                            )
                    elif ctype == "text/plain":
                        try:
                            body_plain += part.get_content()
                        except Exception:
                            body_plain += (part.get_payload(decode=True) or b"").decode(
                                "utf-8", "ignore"
                            )
            else:
                ctype = (msg.get_content_type() or "").lower()
                payload = (msg.get_payload(decode=True) or b"").decode(
                    "utf-8", "ignore"
                )
                if ctype == "text/html":
                    body_html = payload
                else:
                    body_plain = payload
        except Exception:
            pass

        return body_html, body_plain

    def _build_imap_attachments(
        self, msg: Any, account: Any, folder_name: str, uid: int, index_id: int
    ) -> List[Any]:
        """
        Build attachment list for IMAP message by materializing to ir.attachment.

        ARCHITECTURE: Uses AttachmentCacheService to materialize all IMAP attachments.
        All attachments are stored in ir.attachment linked to the SSOT row
        (maildesk.message_index) and served via standard Odoo routes.
        """
        from ...application.services.attachment_cache_service import (
            AttachmentCacheService,
            AttachmentMaterializeRequest,
            AttachmentSource,
        )
        from ...infrastructure.repositories.attachment_repository import (
            AttachmentRepository,
        )

        requests: List[AttachmentMaterializeRequest] = []
        part_index = 0
        seen_cids: set[str] = set()

        for part in msg.walk():
            # Skip container parts
            if part.is_multipart():
                continue

            ctype = (part.get_content_type() or "").lower()
            disp = (part.get_content_disposition() or "").lower()
            content_id = (part.get("Content-ID") or "").strip("<>").strip() or None

            # Skip pure body parts without CID and without attachment disposition
            if (
                ctype in ("text/plain", "text/html")
                and not content_id
                and disp != "attachment"
            ):
                continue

            # Only materialize parts that are explicitly attachments/inline or have a CID
            if disp not in ("attachment", "inline") and not content_id:
                continue

            payload = part.get_payload(decode=True) or b""
            size = len(payload)

            # Some inline parts have no filename; keep deterministic name
            name = (
                part.get_filename()
                or (content_id if content_id else None)
                or ("inline" if disp == "inline" else "attachment")
            )
            mimetype = ctype or "application/octet-stream"

            # Avoid double materialization of the same CID
            if content_id and content_id in seen_cids:
                part_index += 1
                continue

            account_id = self._deps.account_id(account)
            part_index += 1

            req = AttachmentMaterializeRequest(
                source=AttachmentSource.PROVIDER_IMAP,
                name=name,
                mimetype=mimetype,
                size=size,
                account_id=account_id,
                content_id=content_id,
                provider_attachment_id=str(part_index),
                provider_message_id=str(uid),
                provider_url=folder_name,  # Store folder for context
                attachment_data=payload,  # Pre-fetched bytes (Option B)
            )
            requests.append(req)
            if content_id:
                seen_cids.add(content_id)

        # Materialize via service
        # IMAP attachments are ALWAYS materialized (per architectural requirements)
        repo = AttachmentRepository(self._deps.env_user())
        service = AttachmentCacheService(repo)
        dtos = service.materialize_from_provider(
            requests, int(index_id), force_materialize=True
        )

        # Convert DTOs to JSON (FileModel computes URLs and type booleans from these)
        return [
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

    def _apply_imap_state_overlays(
        self, account: Any, folder_name: str, uid: str, rec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply state overlays from maildesk.email_state."""
        st = self._deps.state_search(
            [
                ("account_id", "=", self._deps.account_id(account)),
                ("folder", "=", folder_name),
                ("uid", "=", uid),
            ],
            limit=1,
        )

        if st:
            seen_val = getattr(st, "seen", None)
            starred_val = getattr(st, "starred", None)

            if seen_val is not None:
                rec["is_read"] = bool(seen_val)
            if starred_val is not None:
                rec["is_starred"] = bool(starred_val)

        return rec
