# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Mailbox Sync.

Defines Odoo ORM models and server-side APIs for Mailbox Sync.
Layer: odoo models.
"""

import logging

from odoo import SUPERUSER_ID, api, models
from odoo.exceptions import UserError

from ..infrastructure.providers.imap.pool import get_pool as _imap_get_pool
from ..application.services.access_control import AccessControl
from ..application.services.email_text_helper import EmailTextHelper
from ..application.use_cases import (
    SyncImapFolderIncremental,
    BulkFlagsParams,
    BulkSetFlags,
    CreatePartnerFromMessage,
    CreatePartnerFromMessageParams,
    DeleteDraft,
    DeleteDraftParams,
    FetchThread,
    FetchThreadParams,
    ListMessagesSsot,
    ListMessagesParams,
    LoadDraft,
    LoadDraftParams,
    MoveMessages,
    MoveMessagesParams,
    OpenLinkedDocument,
    OpenLinkedDocumentParams,
    OpenMessage,
    OpenMessageParams,
    OpenThreadMessages,
    OpenThreadMessagesParams,
    SaveDraft,
    SaveDraftParams,
    SendEmail,
    SendEmailParams,
    SetFlags,
    SetFlagsParams,
    TrustPartner,
    TrustPartnerParams,
)
from ..application.use_cases.sync_gmail_incremental import SyncGmailIncremental
from ..application.use_cases.sync_outlook_delta import SyncOutlookDelta
from ..domain.policies.mutation_policy import MutationContext, MutationIntent
from ..infrastructure.adapters.bus_notification_adapter import BusNotificationAdapter
from ..infrastructure.adapters.create_partner_adapter import CreatePartnerAdapter
from ..infrastructure.adapters.fetch_thread_adapter import FetchThreadAdapter
from ..infrastructure.adapters.get_attachments_adapter import GetAttachmentsAdapter
from ..infrastructure.adapters.ssot_list_adapter import SsotListMessagesAdapter
from ..infrastructure.adapters.message_meta_bulk_adapter import MessageMetaBulkAdapter
from ..infrastructure.adapters.move_messages_adapter import MoveMessagesAdapter
from ..infrastructure.adapters.open_document_adapter import OpenDocumentAdapter
from ..infrastructure.adapters.open_message_adapter import OpenMessageAdapter
from ..infrastructure.adapters.open_thread_messages_adapter import (
    OpenThreadMessagesAdapter,
)
from ..infrastructure.adapters.set_flags_adapter import SetFlagsAdapter
from ..infrastructure.adapters.trust_partner_adapter import TrustPartnerAdapter
from ..infrastructure.adapters.unread_counts_adapter import UnreadCountsAdapter
from ..infrastructure.persistence.draft_repository import DraftRepository
from ..infrastructure.persistence.email_state_repository import EmailStateRepository

from ..infrastructure.repositories.message_index_projection_repo import (
    MessageIndexProjectionRepo,
)
from ..infrastructure.repositories.message_index_query_repo import MessageIndexQueryRepo
from ..infrastructure.persistence.message_index_repository import (
    MessageIndexRepository,
)
from ..infrastructure.adapters.provider_delete_adapter import ProviderDeleteAdapter
from ..application.use_cases.delete_messages_unified import (
    DeleteMessagesUnified,
    DeleteMessagesParams as UnifiedDeleteParams,
)
from ..application.use_cases.update_tags_unified import (
    UpdateTagsUnified,
    UpdateTagsParams as UnifiedTagsParams,
)
from ..application.services.tag_update_service import TagUpdateService
from ..application.errors import MailDeskError

_logger = logging.getLogger(__name__)


# Compatibility shim for `maildesk_mail_client_pro` imports.
# Older/PRO code imports `get_pool` from this module-level namespace.
def get_pool(account):
    return _imap_get_pool(account)


class MailboxSync(models.AbstractModel):
    _name = "mailbox.sync"
    _description = "Mailbox Sync Service"

    def _user_accounts(self):
        """
        Return the list of mailbox account records that the current user is
        authorized to access.
        """
        Account = self.env["mailbox.account"]
        return Account.search(
            [("access_user_ids", "in", [self.env.uid])], order="sequence, name"
        )

    @api.model
    def message_meta_bulk(self, account_id, folder_id, uids):
        """
        Retrieve a batch of message metadata for the specified folder and UIDs.
        Delegates to the infrastructure layer to handle provider-specific logic.
        """
        adapter = MessageMetaBulkAdapter(self.env)
        return adapter.fetch_bulk(account_id, folder_id, uids)

    @api.model
    def message_search_load(
        self,
        account_id=None,
        folder_id=None,
        filter=None,
        search=None,
        offset=0,
        limit=30,
        partner_id=None,
        email_from=None,
        tag_ids=None,
    ):
        """
        Execute a search and return a paginated list of message metadata.
        This provides a high-level API for the UI to load message summaries
        based on various filters and search criteria.
        """
        query_repo = MessageIndexQueryRepo(self.env)
        ssot_adapter = SsotListMessagesAdapter(self.env, query_repo)
        params = ListMessagesParams(
            account_id=int(account_id) if account_id else None,
            folder_id=int(folder_id) if folder_id else None,
            filter=filter,
            search=search,
            offset=int(offset or 0),
            limit=int(limit or 30),
            tag_ids=tag_ids or [],
            partner_id=partner_id,
            email_from=email_from,
        )
        # SsotListMessagesAdapter implements ListMessagesSsotDeps directly
        use_case = ListMessagesSsot(ssot_adapter)
        result = use_case.execute(params)
        result_dict = result  # Result is already a dict

        # Fix pagination contract: add hasMore flag for infinite scroll
        total = result_dict.get("totalMessagesCount", 0)
        current_offset = int(offset or 0)
        current_limit = int(limit or 30)
        records = result_dict.get("records") or []
        num_returned = len(records)

        result_dict["hasMore"] = (current_offset + num_returned) < total
        result_dict["offset"] = current_offset
        result_dict["limit"] = current_limit

        return result_dict

    @api.model
    def poll_for_updates(self, account_id, folder_id=None):
        """
        UI-triggered polling endpoint for near-realtime sync.

        Called by frontend JS ticker while mailbox view is open.
        Uses per-account lease (SKIP LOCKED) to deduplicate concurrent calls.

        Multiple tabs calling this will result in only ONE sync per account.

        Args:
            account_id: Account ID to poll
            folder_id: Optional folder ID (for folder-specific sync)

        Returns:
            {
                "has_updates": bool,  # True ONLY if NEW messages found
                "last_sync_at": str,  # ISO timestamp of last sync
                "synced": bool,       # True if THIS call performed sync
            }
        """
        if not account_id:
            return {"has_updates": False, "last_sync_at": None, "synced": False}

        # Use lease mechanism to prevent concurrent syncs
        Account = self.env["mailbox.account"]  # Define Account model here
        self.env.cr.execute(
            """
            SELECT id FROM mailbox_account
            WHERE id = %s
            FOR NO KEY UPDATE SKIP LOCKED
            """,
            (account_id,),
        )

        if not self.env.cr.fetchone():
            _logger.info(f"Account {account_id} is already being synced, skipping poll")
            return {"has_updates": False, "last_sync_at": None, "synced": False}

        account = Account.browse(account_id)
        if not account.exists():
            return {"has_updates": False, "last_sync_at": None, "synced": False}

        result = {"has_updates": False, "synced": True, "last_sync_at": None}
        new_messages_count = 0

        if account.is_gmail:
            notifier = BusNotificationAdapter(self.env)
            use_case = SyncGmailIncremental(self.env, notifier=notifier)
            sync_result = use_case.execute(account.id)
            new_messages_count = sync_result.get("new_count", 0)
            result.update(
                {
                    "has_updates": new_messages_count > 0,
                    "last_sync_at": account.gmail_last_sync_at.isoformat()
                    if account.gmail_last_sync_at
                    else None,
                }
            )
        elif account.is_outlook:
            notifier = BusNotificationAdapter(self.env)
            use_case = SyncOutlookDelta(self.env, notifier=notifier)
            sync_result = use_case.execute(account.id)
            new_messages_count = sync_result.get("new_count", 0)
            result.update(
                {
                    "has_updates": new_messages_count > 0,
                    "last_sync_at": account.gmail_last_sync_at.isoformat()
                    if account.gmail_last_sync_at
                    else None,
                }
            )
        elif not account.is_gmail and not account.is_outlook:
            notifier = BusNotificationAdapter(self.env)
            use_case = SyncImapFolderIncremental(self.env, notifier=notifier)
            sync_result = use_case.execute(account.id)
            new_messages_count = sync_result.get("new_count", 0) or sync_result.get(
                "fetched", 0
            )
            result.update(
                {
                    "has_updates": new_messages_count > 0,
                    "last_sync_at": account.gmail_last_sync_at.isoformat()
                    if account.gmail_last_sync_at
                    else None,
                }
            )

        _logger.info(
            f"[Poll] Account {account_id}: synced={result['synced']}, "
            f"has_updates={result['has_updates']} (new: {new_messages_count})"
        )
        return result

    @api.model
    def get_message_with_attachments(self, params):
        """
        Fetch full details for a specific message, including its body content
        and list of attachments.
        """
        if isinstance(params, list) and params:
            params = params[0]

        index_id = params.get("index_id") or params.get("id")
        message_uid = params.get("uid") or params.get("message_id") or ""
        folder_id = params.get("folder_id")
        account_id = params.get("account_id")
        is_internal_draft = params.get("is_internal_draft")

        deps = OpenMessageAdapter(self.env)
        open_params = OpenMessageParams(
            uid=message_uid,
            index_id=int(index_id) if index_id else None,
            folder_id=folder_id,
            account_id=account_id,
            is_internal_draft=is_internal_draft,
        )
        try:
            result = OpenMessage(deps).execute(open_params)
            return result
        except MailDeskError as e:
            raise UserError(str(e)) from e

    @api.model
    def _build_thread_lazy(
        self, account, folder_name, msg_id, checked_folders=None, chain=None
    ):
        """
        Build a thread chain by traversing message references and parent IDs.
        """
        deps = FetchThreadAdapter(self.env)
        fetch_params = FetchThreadParams(
            account=account,
            message_id=msg_id,
            folder_name=folder_name,
            include_bodies=True,
        )
        return FetchThread(deps).execute(fetch_params)

    @api.model
    def fetch_thread_messages(self, thread_id, account_id=None):
        """
        Fetch all messages in a thread with full body content.
        Used by the frontend thread view to display conversation history.

        For Gmail: Uses thread_id directly with Gmail Threads API.
        For IMAP/Outlook: Uses message_id to chase references headers.

        Args:
            thread_id: The thread identifier (Gmail threadId or Message-ID)
            account_id: Optional account ID (uses current filter if not provided)

        Returns:
            list: List of message DTOs with body_original, attachments, etc.
                  Sorted by date ascending (oldest first) for conversation display.
        """
        return self.open_thread_messages(thread_id, account_id=account_id)

    @api.model
    def open_thread_messages(self, thread_id, account_id=None):
        """
        Open a thread in a single server roundtrip.

        This is a cache-only read. Hydration happens exclusively via
        `get_message_with_attachments` (OpenMessage).
        """
        if not thread_id:
            return []

        if account_id:
            account = self.env["mailbox.account"].browse(int(account_id)).exists()
            if not account:
                return []
        else:
            accounts = self._user_accounts()
            if not accounts:
                return []
            account = accounts[0]

        deps = OpenThreadMessagesAdapter(self.env)
        params = OpenThreadMessagesParams(
            account_id=int(account.id),
            thread_id=str(thread_id),
            include_bodies=True,
        )
        return OpenThreadMessages(deps).execute(params)

    @api.model
    def get_message_attachments(self, account_id, folder, uid):
        """
        Return the list of attachment metadata for a specific message.
        """
        adapter = GetAttachmentsAdapter(self.env)
        return adapter.get_attachments(account_id, folder, uid)

    @api.model
    def unread_counts_for_folder(
        self,
        account_id,
        folder_id,
        flt=None,
        text=None,
        partner_id=None,
        email_from=None,
    ):
        """
        Return the count of unread messages for a specific folder and filter.
        """
        adapter = UnreadCountsAdapter(self.env)
        return adapter.get_counts(
            account_id, folder_id, flt, text, partner_id, email_from
        )

    @api.model
    def get_context_unread_counts(self, account_id, partner_id=None):
        """
        Get distribution of unread counts per folder for a specific context (Partner).
        Used when a "Partner Filter" is active.
        """
        if not partner_id:
            return {}

        Partner = self.env["res.partner"].browse(int(partner_id))
        if not Partner.exists():
            return {}

        adapter = UnreadCountsAdapter(self.env)
        email_filter = (
            Partner._maildesk_email_match()
            if hasattr(Partner, "_maildesk_email_match")
            else (Partner.email or "").strip().lower()
        )
        if not email_filter:
            return {}
        return adapter.get_partner_unread_distribution(account_id, email_filter)

    @api.model
    def action_open_create_partner(
        self, message_id=None, email_from=None, sender_display_name=None
    ):
        """
        Initialize the creation of a partner record from an email message.
        """
        deps = CreatePartnerAdapter(self.env)
        return CreatePartnerFromMessage(deps).execute(
            CreatePartnerFromMessageParams(
                message_id=message_id,
                email_from=email_from,
                sender_display_name=sender_display_name,
            )
        )

    @api.model
    def action_open_create_task(
        self, message_id=None, email_from=None, subject=None, body=None
    ):
        """
        Open a new project.task form pre-filled with data from the email message.
        """
        context = {
            "default_name": subject or "",
            "default_description": body or "",
        }
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.task",
            "views": [(False, "form")],
            "target": "new",
            "context": context,
        }

    @api.model
    def action_open_create_ticket(
        self, message_id=None, email_from=None, subject=None, body=None
    ):
        """
        Open a new helpdesk.ticket form pre-filled with data from the email message.
        """
        context = {
            "default_name": subject or "",
            "default_description": body or "",
        }
        return {
            "type": "ir.actions.act_window",
            "res_model": "helpdesk.ticket",
            "views": [(False, "form")],
            "target": "new",
            "context": context,
        }

    @api.model
    def set_flags(self, ids, is_read=None, is_starred=None, folder_id=None):
        """
        Update the read and starred status of one or more messages.
        """
        # Security: ensure the caller can access the underlying mailbox account(s)
        # for all message_index ids being mutated.
        Index = self.env["maildesk.message_index"].sudo()
        msg_ids = [int(i) for i in (ids or [])]
        index_recs = Index.browse(msg_ids).exists()
        for account in index_recs.mapped("account_id"):
            AccessControl(self.env).check_account_access(account)

        state_repo = EmailStateRepository(self.env)
        mutation_context = MutationContext(
            intent=MutationIntent.UI,
            source="set_flags",
        )

        projection_repo = MessageIndexProjectionRepo(self.env)
        deps = SetFlagsAdapter(self.env, state_repo, mutation_context, projection_repo)
        params = SetFlagsParams(
            message_ids=ids,
            is_read=is_read,
            is_starred=is_starred,
            folder_id=folder_id,
        )
        notifier = BusNotificationAdapter(self.env)
        return SetFlags(deps, notifier=notifier).execute(params)

    @api.model
    def set_flags_bulk(self, ops, folder_id=None):
        """
        Apply flag updates in bulk for cross-provider optimization.
        """
        state_repo = EmailStateRepository(self.env)
        mutation_context = MutationContext(
            intent=MutationIntent.UI,
            source="set_flags_bulk",
            context_data=self.env.context.get("maildesk_mutation_context") or {},
        )

        # Import repository (Clean Architecture: no ORM in adapters)
        projection_repo = MessageIndexProjectionRepo(self.env)
        deps = SetFlagsAdapter(self.env, state_repo, mutation_context, projection_repo)
        params = BulkFlagsParams(operations=ops, folder_id=folder_id)
        notifier = BusNotificationAdapter(self.env)
        return BulkSetFlags(deps, notifier=notifier).execute(params)

    @api.model
    def move_messages_to_folder(self, ids, target_folder_id):
        """
        Move specified messages to a target mailbox folder.
        """
        state_repo = EmailStateRepository(self.env)
        mutation_context = MutationContext(
            intent=MutationIntent.UI,
            source="move_messages_to_folder",
            context_data=self.env.context.get("maildesk_mutation_context") or {},
        )

        projection_repo = MessageIndexProjectionRepo(self.env)
        deps = MoveMessagesAdapter(
            self.env, state_repo, mutation_context, projection_repo
        )
        params = MoveMessagesParams(message_ids=ids, target_folder_id=target_folder_id)
        notifier = BusNotificationAdapter(self.env)
        return MoveMessages(deps, notifier=notifier).execute(params)

    @api.model
    def update_tags(self, message_uids, tag_ids):
        """Update tags for messages (supports both drafts and message_index)."""
        draft_repo = DraftRepository(self.env)
        index_repo = MessageIndexRepository(self.env)
        tag_service = TagUpdateService(self.env)
        notifier = BusNotificationAdapter(self.env)

        use_case = UpdateTagsUnified(
            draft_repo=draft_repo,
            index_repo=index_repo,
            tag_service=tag_service,
            notifier=notifier,
        )

        params = UnifiedTagsParams(
            message_ids=message_uids or [], tag_ids=tag_ids or []
        )
        use_case.execute(params)
        return True

    def _to_list(self, txt):
        """
        Convert a multi-line string into a list of trimmed strings.
        """
        if not txt:
            return []
        return [x.strip() for x in txt.splitlines() if x.strip()]

    def _to_text(self, lst):
        """
        Convert a list of strings into a single multi-line string.
        """
        return "\n".join([x.strip() for x in (lst or []) if x])

    @api.model
    def save_draft(self, **kw):
        """
        Persist a message draft to the local store and optionally notify
        the provider if necessary.
        """
        account = self.env["mailbox.account"].browse(int(kw.get("account_id") or 0))
        AccessControl(self.env).check_account_access(account)

        draft_repo = DraftRepository(self.env)
        text_helper = EmailTextHelper()

        att_ids = kw.get("attachment_ids") or []

        params = SaveDraftParams(
            account_id=account.id,
            draft_id=int(kw.get("draft_id")) if kw.get("draft_id") else None,
            subject=kw.get("subject"),
            body_html=kw.get("body_html"),
            to=text_helper.to_list(kw.get("to_emails")),
            cc=text_helper.to_list(kw.get("cc_emails")),
            bcc=text_helper.to_list(kw.get("bcc_emails")),
            attachment_ids=[int(id) for id in att_ids if isinstance(id, int)],
            request_read_receipt=bool(kw.get("request_read_receipt")),
            request_delivery_receipt=bool(kw.get("request_delivery_receipt")),
            sender_display_name=kw.get("sender_display_name"),
            reply_to_message_id=kw.get("reply_to_message_id"),
            reply_to_cache_uid=kw.get("reply_to_cache_uid"),
            model=kw.get("model"),
            res_id=int(kw.get("res_id")) if kw.get("res_id") else None,
        )

        return SaveDraft(draft_repo, text_helper, self.env).execute(params)

    @api.model
    def delete_messages(self, ids, folder_id=None):
        """
        Delete specified messages from the mailbox.

        Handles:
        - Drafts (maildesk.draft) → direct delete
        - Local sent messages (uid starts with 'local-') → direct delete from message_index
        - Regular provider messages → delete via email_state overlay
        """
        draft_repo = DraftRepository(self.env)
        index_repo = MessageIndexRepository(self.env)
        access_control = AccessControl(self.env)
        notifier = BusNotificationAdapter(self.env)
        provider_delete = ProviderDeleteAdapter(self.env, notifier)

        use_case = DeleteMessagesUnified(
            draft_repo=draft_repo,
            index_repo=index_repo,
            access_control=access_control,
            provider_delete=provider_delete,
        )

        params = UnifiedDeleteParams(message_ids=ids or [], folder_id=folder_id)
        use_case.execute(params)
        return True

    @api.model
    def update_draft(self, draft_id, **kw):
        """
        Update an existing draft with new content.
        """
        kw = dict(kw or {})
        kw["draft_id"] = draft_id
        return self.save_draft(**kw)

    @api.model
    def load_draft(self, draft_id):
        """
        Load a specific draft's content for editing.
        """
        draft_repo = DraftRepository(self.env)
        draft = draft_repo.browse(draft_id)
        if draft_repo.exists(draft):
            AccessControl(self.env).check_account_access(draft.account_id)

        text_helper = EmailTextHelper()
        params = LoadDraftParams(draft_id=int(draft_id))

        try:
            return LoadDraft(draft_repo, text_helper).execute(params)
        except ValueError as e:
            raise UserError(str(e)) from e

    @api.model
    def delete_draft(self, draft_id):
        """
        Permanently remove a draft from the system.
        """
        draft_repo = DraftRepository(self.env)
        draft = draft_repo.browse(draft_id)
        if draft_repo.exists(draft):
            AccessControl(self.env).check_account_access(draft.account_id)

        params = DeleteDraftParams(draft_id=int(draft_id))
        DeleteDraft(draft_repo).execute(params)
        return True

    @api.model
    def send_email(self, **kw):
        """
        Send an email message using the specified parameters, or from a draft.
        """
        use_case = SendEmail(self.env)
        params = SendEmailParams(
            account_id=int(kw["account_id"]) if kw.get("account_id") else None,
            draft_id=int(kw["draft_id"]) if kw.get("draft_id") else None,
            subject=kw.get("subject"),
            body_html=kw.get("body_html") or kw.get("body"),
            to=kw.get("to") or kw.get("to_emails") or [],
            cc=kw.get("cc") or kw.get("cc_emails") or [],
            bcc=kw.get("bcc") or kw.get("bcc_emails") or [],
            attachment_ids=kw.get("attachment_ids") or kw.get("attachments") or [],
            reply_to_message_id=kw.get("reply_to_message_id"),
            request_delivery_receipt=bool(kw.get("request_delivery_receipt")),
            request_read_receipt=bool(kw.get("request_read_receipt")),
            sender_display_name=kw.get("from_display"),
        )
        return use_case.execute(params)

    def _check_account_access(self, account):
        """
        Internal helper to verify the current user has access to the account.
        """
        if self.env.uid == SUPERUSER_ID:
            return
        if not account:
            raise UserError(self.env._("Mailbox account is required."))
        if (
            not self.env.user.has_group("maildesk_mail_client.group_mailbox_admin")
            and self.env.user not in account.access_user_ids
        ):
            raise UserError(
                self.env._("You do not have access to this mailbox account.")
            )

    @api.model
    def mark_partner_trusted(self, message):
        """
        Mark the sender of the given message as a trusted partner.
        """
        deps = TrustPartnerAdapter(self.env)
        return TrustPartner(deps).execute(TrustPartnerParams(message=message))

    @api.model
    def get_open_document_action(self, model, res_id):
        """
        Return the Odoo action to open a linked document record.
        """
        deps = OpenDocumentAdapter(self.env)
        return OpenLinkedDocument(deps).execute(
            OpenLinkedDocumentParams(model=model, res_id=res_id)
        )
