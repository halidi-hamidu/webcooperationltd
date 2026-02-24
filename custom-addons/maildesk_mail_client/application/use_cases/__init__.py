# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Use-case implementations (Phase A extraction, not wired).
"""

from .create_partner_from_message import (
    CreatePartnerFromMessage,
    CreatePartnerFromMessageDeps,
    CreatePartnerFromMessageParams,
)
from .delete_draft import DeleteDraft, DeleteDraftParams
from .fetch_thread import FetchThread, FetchThreadDeps, FetchThreadParams
from .list_messages_ssot import ListMessagesParams, ListMessagesSsot
from .sync_gmail_history import SyncGmailHistory
from .sync_imap_folder import SyncImapFolderIncremental
from .scan_imap_folders import ScanImapFolders
from .load_draft import LoadDraft, LoadDraftParams
from .open_linked_document import (
    OpenLinkedDocument,
    OpenLinkedDocumentDeps,
    OpenLinkedDocumentParams,
)
from .open_message import OpenMessage, OpenMessageDeps, OpenMessageParams
from .open_thread_messages import (
    OpenThreadMessages,
    OpenThreadMessagesDeps,
    OpenThreadMessagesParams,
)
from .save_draft import SaveDraft, SaveDraftParams
from .send_email import SendEmail, SendEmailParams
from .ingest_queue import (
    EnqueueIngestForMessageIndex,
    EnqueueIngestForMessageIndexParams,
    ProcessIngestQueueBatch,
    ProcessIngestQueueBatchParams,
    RecoverStuckIngestJobs,
    RecoverStuckIngestJobsParams,
    ScanSSOTForIngestion,
    ScanSSOTForIngestionParams,
)
from .trust_partner import (
    TrustPartner,
    TrustPartnerDeps,
    TrustPartnerParams,
)
from .prepare_reply import PrepareReply, PrepareReplyDeps, PrepareReplyParams
from .prepare_forward import PrepareForward, PrepareForwardDeps, PrepareForwardParams
from .sanitize_message_body import (
    SanitizeMessageBody,
    SanitizeMessageBodyDeps,
    SanitizeMessageBodyParams,
)
from .ui_actions import (
    BulkFlagsParams,
    BulkSetFlags,
    DeleteMessages,
    DeleteMessagesParams,
    MoveMessages,
    MoveMessagesParams,
    SetFlags,
    SetFlagsParams,
    UIActionDeps,
    UpdateTags,
    UpdateTagsParams,
)
from .delete_messages_unified import (
    DeleteMessagesUnified,
    DeleteMessagesParams as UnifiedDeleteParams,
)
from .update_tags_unified import (
    UpdateTagsUnified,
    UpdateTagsParams as UnifiedTagsParams,
)

__all__ = [
    "DeleteMessagesUnified",
    "UnifiedDeleteParams",
    "UpdateTagsUnified",
    "UnifiedTagsParams",
    "ListMessagesSsot",
    "ListMessagesParams",
    "SyncGmailHistory",
    "SyncImapFolderIncremental",
    "ScanImapFolders",
    "OpenMessage",
    "OpenMessageParams",
    "OpenMessageDeps",
    "OpenThreadMessages",
    "OpenThreadMessagesParams",
    "OpenThreadMessagesDeps",
    "FetchThread",
    "FetchThreadParams",
    "FetchThreadDeps",
    "SetFlags",
    "SetFlagsParams",
    "BulkSetFlags",
    "BulkFlagsParams",
    "MoveMessages",
    "MoveMessagesParams",
    "DeleteMessages",
    "DeleteMessagesParams",
    "UpdateTags",
    "UpdateTagsParams",
    "UIActionDeps",
    "OpenLinkedDocument",
    "OpenLinkedDocumentParams",
    "OpenLinkedDocumentDeps",
    "TrustPartner",
    "TrustPartnerParams",
    "TrustPartnerDeps",
    "CreatePartnerFromMessage",
    "CreatePartnerFromMessageParams",
    "CreatePartnerFromMessageDeps",
    "DeleteDraft",
    "DeleteDraftParams",
    "SaveDraft",
    "SaveDraftParams",
    "LoadDraft",
    "LoadDraftParams",
    "SendEmail",
    "SendEmailParams",
    "EnqueueIngestForMessageIndex",
    "EnqueueIngestForMessageIndexParams",
    "ScanSSOTForIngestion",
    "ScanSSOTForIngestionParams",
    "ProcessIngestQueueBatch",
    "ProcessIngestQueueBatchParams",
    "RecoverStuckIngestJobs",
    "RecoverStuckIngestJobsParams",
    "PrepareReply",
    "PrepareReplyParams",
    "PrepareReplyDeps",
    "PrepareForward",
    "PrepareForwardParams",
    "PrepareForwardDeps",
    "SanitizeMessageBody",
    "SanitizeMessageBodyParams",
    "SanitizeMessageBodyDeps",
]
