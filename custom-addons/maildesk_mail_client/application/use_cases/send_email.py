# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
SendEmail Use-Case: Handles sending emails via SMTP/Providers.
Orchestrates MIME building, sending, IMAP appending, and draft lifecycle.
"""

import logging
import uuid
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from odoo import fields
from bs4 import BeautifulSoup

from ...infrastructure.adapters.bus_notification_adapter import BusNotificationAdapter
from ...infrastructure.email.imap_sent_appender import ImapSentAppender
from ...infrastructure.email.mime_builder import MimeBuilder
from ...infrastructure.email.sent_append_policy import need_manual_sent_append
from ...infrastructure.email.smtp_sender import SmtpSender
from ...infrastructure.persistence.draft_repository import DraftRepository
from ...infrastructure.repositories.attachment_repository import AttachmentRepository
from ...domain.services.normalization import (
    build_references_header,
    msgid_header,
    norm_msgid,
)
from ..services.access_control import AccessControl
from ..services.attachment_cache_service import AttachmentCacheService
from ..services.normalize_outgoing_html import NormalizeOutgoingHtml

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SendEmailParams:
    """Parameters for sending an email."""

    account_id: Optional[int] = None
    draft_id: Optional[int] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    to: List[str] = field(default_factory=list)
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    attachment_ids: List[int] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    request_read_receipt: bool = False
    request_delivery_receipt: bool = False
    sender_display_name: Optional[str] = None


class SendEmail:
    """
    Use-case: Send an email.

    Handles:
    - Account access validation
    - Draft resolution (if draft_id provided)
    - MIME construction
    - SMTP sending
    - IMAP Sent folder appending
    - Draft deletion (on success)
    """

    def __init__(self, env):
        self._env = env
        self._draft_repo = DraftRepository(env)
        self._access_control = AccessControl(env)
        self._mime_builder = MimeBuilder(env)
        self._smtp_sender = SmtpSender(env)
        self._imap_appender = ImapSentAppender(env)

    def execute(self, params: SendEmailParams) -> dict:
        """
        Execute email sending.

        Args:
            params: SendEmailParams

        Returns:
            Dict with "message_id"
        """
        # 1. Resolve Account and Data (Draft vs explicit)
        account = None
        draft = None

        # Prepare data containers (mutable for draft resolution)
        subject = params.subject or ""
        body_html = params.body_html or ""
        to_list = params.to
        cc_list = params.cc
        bcc_list = params.bcc
        att_ids = params.attachment_ids
        reply_mid = params.reply_to_message_id
        req_read = params.request_read_receipt
        req_delivery = params.request_delivery_receipt
        from_name = params.sender_display_name

        if params.draft_id:
            draft = self._draft_repo.browse(params.draft_id)
            if self._draft_repo.exists(draft):
                account = draft.account_id
                # Overlay draft data ONLY if params are missing (fallback)
                # This ensures UI edits take precedence over saved draft state.
                subject = subject or (draft.subject or "")
                body_html = body_html or (draft.body_html or "")

                # For recipients, merge or fallback?
                # Standard behavior: UI sends full list.
                # If UI list is empty, it means user cleared it OR invoked from list view.
                # We assume params.to provided from UI is authoritative if present.

                if not to_list:
                    to_list = self._parse_emails(draft.to_emails)
                if not cc_list:
                    cc_list = self._parse_emails(draft.cc_emails)
                if not bcc_list:
                    bcc_list = self._parse_emails(draft.bcc_emails)

                if not att_ids:
                    att_ids = draft.attachment_ids.ids

                reply_mid = reply_mid or draft.reply_to_message_id
                # Booleans: explicitly use params if provided? They default to False/None.
                # If param is False but draft is True -> keep draft?
                # Params defaults are False.
                # Let's trust params.request_read_receipt is authoritative from UI checkbox.
                # Wait, if checkbox is UNCHECKED, param is False. If draft was Checked.
                # UI should reflect draft state on load. So on Send, UI state is final.
                # So we keep defaults (False) if UI sends False.
                # Only use draft if we didn't get params (e.g. explicit headless call).
                # But params is dataclass, always has fields.

                # Logic compromise:
                # If params are empty (default), use draft.
                # But boolean defaults are False.
                # Assuming UI sends explicit True/False.
                # We assume provided params are correct.

                from_name = from_name or draft.sender_display_name

        if not account and params.account_id:
            account = self._env["mailbox.account"].browse(params.account_id)

        # 2. Validate Access
        self._access_control.check_account_access(account)

        # 3. NORMALIZE OUTGOING HTML (defensive - in case draft wasn't normalized)
        # This is idempotent: already-normalized HTML passes through unchanged.
        normalizer = NormalizeOutgoingHtml(self._env)
        body_html_normalized, _ = normalizer.normalize(body_html, att_ids)

        # Threading inputs: pass parent's References chain to MIME builder (full RFC 5322 chain).
        reply_references = ""
        if reply_mid:
            Index = self._env["maildesk.message_index"].sudo()
            parent = Index.search(
                [
                    ("account_id", "=", account.id),
                    "|",
                    ("message_id", "=ilike", reply_mid),
                    ("message_id", "=ilike", msgid_header(reply_mid)),
                ],
                limit=1,
            )
            if parent and parent.references_hdr:
                reply_references = parent.references_hdr

        outgoing_id = f"maildesk-{uuid.uuid4()}"

        # 4. Build MIME Message
        msg, mid = self._mime_builder.build(
            account=account,
            subject=subject,
            body_html=body_html_normalized,  # NORMALIZED
            to=to_list,
            cc=cc_list,
            bcc=bcc_list,
            reply_message_id=reply_mid,
            reply_references=reply_references,
            attachment_ids=att_ids,
            request_read_receipt=req_read,
            request_delivery_receipt=req_delivery,
            from_display=from_name,
            outgoing_id=outgoing_id,
        )

        # 4. Send via SMTP
        envelope_to_addrs = (to_list or []) + (cc_list or []) + (bcc_list or [])
        self._smtp_sender.send(account, msg, envelope_to_addrs=envelope_to_addrs)

        if need_manual_sent_append(account):
            try:
                self._imap_appender.append(account, msg)
            except Exception:
                _logger.exception(
                    "Error while trying to save sent message to IMAP Sent"
                )

        # 6. Create SSOT entry immediately (SSOT-on-Send)
        self._create_local_sent_entry(
            account=account,
            message_id=mid,
            outgoing_id=outgoing_id,
            subject=subject,
            to_list=to_list,
            cc_list=cc_list,
            bcc_list=bcc_list,
            from_name=from_name or account.sender_name or account.email,
            reply_mid=reply_mid,
            att_ids=att_ids,
            body_html=body_html,
        )

        # 7. Delete Draft (if applicable)
        if draft and self._draft_repo.exists(draft):
            self._draft_repo.delete(draft)

        return {"message_id": mid}

    def _parse_emails(self, text):
        """Helper to parse email string to list (matches legacy _to_list)."""
        if not text:
            return []
        return [e.strip() for e in text.split(",") if e.strip()]

    def _generate_preview(self, body_html):
        """Generate a text preview from HTML body."""
        if not body_html:
            return ""
        try:
            if not BeautifulSoup:
                return ""
            soup = BeautifulSoup(body_html, "html.parser")
            for t in soup(
                ["style", "script", "head", "meta", "link", "svg", "noscript"]
            ):
                t.decompose()
            for a in soup.find_all("a", href=True):
                # Optionally append URL, but for preview we usually just want text
                # Logic in mime_builder appends URL, let's skip for cleaner preview?
                # Actually, preview usually needs content.
                # Let's keep it simple: get text.
                pass

            txt = soup.get_text(separator=" ").strip()
            # Collapse whitespace
            text = " ".join(txt.split())
            # Truncate
            return text[:200]
        except Exception:
            _logger.exception("Error generating preview")
            return ""

    def _create_local_sent_entry(
        self,
        account,
        message_id,
        outgoing_id,
        subject,
        to_list,
        cc_list,
        bcc_list,
        from_name,
        reply_mid,
        att_ids=None,
        body_html=None,
    ):
        """
        Create SSOT entry immediately for sent message.
        """
        _logger.info(f"[SSOT-on-Send] Creating entry for mid={message_id}...")

        Index = self._env["maildesk.message_index"].sudo()

        # Determine sent folder name
        sent_folder = "Sent"
        folders = (
            self._env["mailbox.folder"]
            .sudo()
            .search(
                [
                    ("account_id", "=", account.id),
                    ("imap_name", "ilike", "sent"),
                ],
                limit=1,
            )
        )
        if folders:
            sent_folder = folders[0].imap_name

        # Resolve threading info from reply_mid
        thread_id = False
        in_reply_to = False
        references_hdr = ""
        if reply_mid:
            # Find parent to get thread_id and references
            parent = Index.search(
                [
                    ("account_id", "=", account.id),
                    "|",
                    ("message_id", "=ilike", reply_mid),
                    ("message_id", "=ilike", msgid_header(reply_mid)),
                ],
                limit=1,
            )
            if parent:
                thread_id = parent.thread_id
                in_reply_to = msgid_header(reply_mid)
                references_hdr = build_references_header(
                    parent.references_hdr or "",
                    reply_mid,
                )
            else:
                in_reply_to = msgid_header(reply_mid)
                references_hdr = build_references_header("", reply_mid)
        else:
            # For non-replies, use the message's own Message-ID-derived thread_id (IMAP/Outlook heuristic).
            thread_id = norm_msgid(message_id)

        # Prepare attachments for SSOT
        has_attachments = False
        if att_ids:
            has_attachments = True

        _logger.info(
            f"[SSOT-on-Send] Preparing values for SSOT entry (mid={message_id})..."
        )

        # Compute sort_ts to ensure message appears at TOP of list
        now_dt = fields.Datetime.now()
        sort_ts = int(now_dt.timestamp())

        # Generate preview
        preview = self._generate_preview(body_html)

        # Create entry
        try:
            vals = {
                "account_id": account.id,
                "provider": "gmail"
                if account.is_gmail
                else ("outlook" if account.is_outlook else "imap"),
                "folder": sent_folder,
                "uid": f"local-{uuid.uuid4()}",
                "message_id": message_id,
                "outgoing_id": outgoing_id,
                "from_addr": account.email,
                "to_addrs": ", ".join(to_list) if to_list else "",
                "cc_addrs": ", ".join(cc_list) if cc_list else "",
                "bcc_addrs": ", ".join(bcc_list) if bcc_list else "",
                "subject": subject or "(no subject)",
                "date": now_dt,
                "sort_ts": sort_ts,
                "sender_display_name": from_name,
                "preview": preview,
                "is_read": True,
                "is_starred": False,
                "has_attachments": has_attachments,
                "local_pending": True,
                "flags": "\\Seen",
                "in_reply_to": in_reply_to,
                "references_hdr": references_hdr,
                "thread_id": thread_id,
            }

            entry = Index.create(vals)
            _logger.info(
                f"[SSOT-on-Send] Index entry created successfully: ID={entry.id}"
            )

            if att_ids:
                Attachment = self._env["ir.attachment"].sudo()
                attachments = Attachment.browse(att_ids)
                # Link to message_index (ownership)
                attachments.write(
                    {"res_model": "maildesk.message_index", "res_id": entry.id}
                )

            # Emit bus event for immediate UI update
            notifier = BusNotificationAdapter(self._env)
            notifier.notify_messages_added(
                account_id=account.id,
                folder=sent_folder,
                uids=[entry.uid],
                origin="send_email",
                index_ids=[entry.id],
                messages=[
                    {
                        "index_id": entry.id,
                        "message_id": message_id,
                        "account_id": account.id,
                        "folder": sent_folder,
                        "uid": entry.uid,
                        "subject": subject or "(no subject)",
                        "preview": preview,
                        "sender_name": from_name,
                        "date": entry.date.isoformat(),
                    }
                ],
            )
            _logger.info(
                f"[SSOT-on-Send] Created local entry: account={account.id}, "
                f"message_id={message_id}, folder={sent_folder}"
            )
        except Exception as e:
            _logger.exception(f"[SSOT-on-Send] FATAL ERROR creating entry: {e}")
            raise e

        # 8. Hydrate UI Cache (Critical for immediate visibility)
        # Cache hydration MUST succeed - if it fails, send should fail
        # Otherwise sent messages can't be opened (no cache, can't fetch from provider)
        self._hydrate_ui_cache(entry, body_html, att_ids)

        # 9. MailDesk UI refresh is driven by bus events emitted above via notifier.

    def _hydrate_ui_cache(self, index_entry, body_html, att_ids):
        """
        Populate maildesk.ui_cache so the message can be opened immediately
        without waiting for server sync or fetching.
        """
        _logger.info(f"[SSOT-on-Send] Hydrating UI cache for index_id={index_entry.id}")

        # Use AttachmentCacheService to materialize attachments
        # Service will:
        # 1. Ensure tokens exist
        # 2. Link attachments to cache for CASCADE delete
        # 3. Build DTOs (pure, immutable)
        attachments_data = []
        if att_ids:
            repo = AttachmentRepository(self._env)
            service = AttachmentCacheService(repo)
            attachments_data = [
                asdict(dto)
                for dto in service.materialize_for_sent_email(att_ids, index_entry.id)
            ]

        _logger.info(
            f"[SSOT-on-Send] Saving body_html length={len(body_html or '')}, attachments={len(attachments_data)}"
        )
        # Use the cache service
        Cache = self._env["maildesk.ui_cache"].sudo()
        Cache.upsert_body_cache(
            index_id=index_entry.id,
            body_html=body_html or "",
            body_text=None,  # Will be generated on demand if needed
            attachments=attachments_data,
            ttl_days=30,  # Keep local sent items cached for a while
        )
        _logger.info(
            f"[SSOT-on-Send] Cache hydration COMPLETE for index_id={index_entry.id}"
        )
