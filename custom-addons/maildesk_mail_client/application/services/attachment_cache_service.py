# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
AttachmentCacheService: Orchestrates attachment materialization and DTO building.

Layer: application
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ...infrastructure.repositories.attachment_repository import (
        AttachmentRepository,
    )

_logger = logging.getLogger(__name__)


class AttachmentSource(Enum):
    """Source type for attachment materialization."""

    LOCAL_SENT = "local_sent"
    LOCAL_DRAFT = "local_draft"
    PROVIDER_GMAIL = "provider_gmail"
    PROVIDER_OUTLOOK = "provider_outlook"
    PROVIDER_IMAP = "provider_imap"


@dataclass(frozen=True)
class AttachmentMaterializeRequest:
    """
    Immutable request object for attachment materialization.

    Attributes:
        source: Origin of attachment (local/provider)
        name: Filename
        mimetype: MIME type
        size: File size in bytes
        account_id: Mailbox account ID
        content_id: CID for inline images
        provider_url: Provider download URL
        provider_attachment_id: Provider attachment ID
        provider_message_id: Provider message ID
        local_attachment_id: ir.attachment ID
        cache_id: maildesk.ui_cache ID for cascade
        attachment_data: Pre-fetched binary data (IMAP)
    """

    source: AttachmentSource
    name: str
    mimetype: str
    size: int
    account_id: int
    content_id: Optional[str] = None
    provider_url: Optional[str] = None
    provider_attachment_id: Optional[str] = None
    provider_message_id: Optional[str] = None
    local_attachment_id: Optional[int] = None
    cache_id: Optional[int] = None
    attachment_data: Optional[bytes] = None


@dataclass(frozen=True)
class AttachmentDTO:
    """
    Immutable attachment DTO for service layer.

    Contains ONLY data fields. FileModel computes:
    - URLs from id, access_token, checksum
    - Type booleans (isImage, isPdf, isViewable) from mimetype

    Attributes:
        id: ir.attachment ID
        name: Filename
        mimetype: MIME type
        size: File size in bytes
        access_token: Security token for public access
        checksum: For unique query param
        content_id: CID for inline images
        type: "binary" or "url"
        extension: File extension
        icon_mimetype: MIME type for icon display
    """

    id: int
    name: str
    mimetype: str
    size: int
    access_token: str
    checksum: str
    content_id: str
    type: str
    extension: str
    icon_mimetype: str


class AttachmentCacheService:
    """
    Attachment materialization orchestrator.

    Single source of truth for attachment policies:
    - When to materialize (lazy vs eager)
    - When to generate tokens
    - When to link to cache (TTL)
    - How to build DTOs
    """

    def __init__(self, repo: "AttachmentRepository"):
        """
        Initialize service with repository.

        Args:
            repo: AttachmentRepository instance
        """
        self._repo = repo

    def materialize_for_sent_email(
        self, attachment_ids: List[int], cache_id: int
    ) -> List[AttachmentDTO]:
        """
        Materialize attachments for sent email.

        Generates tokens and returns DTOs.

        IMPORTANT:
        Attachments are authoritative in `ir.attachment` and should remain linked
        to their business owner (e.g. `maildesk.message_index` for sent messages).
        This method MUST NOT relink them to `maildesk.ui_cache`.

        Args:
            attachment_ids: List of ir.attachment IDs
            cache_id: Kept for backward signature compatibility (unused)

        Returns:
            List of AttachmentDTO with tokens
        """
        dtos = []
        for att_id in attachment_ids:
            self._repo.ensure_token(att_id)
            dtos.append(self._repo.build_dto_from_attachment(att_id))
        return dtos

    def materialize_for_draft(self, attachment_ids: List[int]) -> List[AttachmentDTO]:
        """
        Materialize attachments for draft.

        Generates tokens but no cascade link (draft owns attachments).

        Args:
            attachment_ids: List of ir.attachment IDs

        Returns:
            List of AttachmentDTO with tokens
        """
        dtos = []
        for att_id in attachment_ids:
            self._repo.ensure_token(att_id)
            dtos.append(self._repo.build_dto_from_attachment(att_id))
        return dtos

    def materialize_from_provider(
        self,
        requests: List[AttachmentMaterializeRequest],
        index_id: int,
        force_materialize: bool = False,
    ) -> List[AttachmentDTO]:
        """
        Materialize attachments from provider (Gmail/Outlook/IMAP).

        Policy (canonical):
        - MailDesk UI must not expose provider attachment URLs.
        - If an attachment is returned to the UI, it MUST be materialized into
          `ir.attachment` (type=binary) with an access token.

        Args:
            requests: List of AttachmentMaterializeRequest
            index_id: maildesk.message_index ID (SSOT owner)
            force_materialize: Force local storage for all

        Returns:
            List of AttachmentDTO (binary only)
        """
        import hashlib

        to_materialize = []
        for req in requests:
            is_inline = bool(req.content_id)
            is_imap = req.source == AttachmentSource.PROVIDER_IMAP
            should_materialize = is_inline or force_materialize or is_imap

            if not should_materialize:
                continue
            if not req.attachment_data:
                continue
            to_materialize.append(req)

        dtos = []

        if to_materialize:
            checksums = [
                hashlib.sha1(req.attachment_data).hexdigest() for req in to_materialize
            ]

            existing_map = self._repo.find_by_checksums(
                checksums, res_model="maildesk.message_index", res_id=int(index_id)
            )

            new_attachments = []
            deduplicated_count = 0

            for i, req in enumerate(to_materialize):
                checksum = checksums[i]

                if checksum in existing_map:
                    att_id = existing_map[checksum]
                    self._repo.ensure_token(att_id)
                    dtos.append(self._repo.build_dto_from_attachment(att_id))
                    deduplicated_count += 1
                else:
                    new_attachments.append(
                        {
                            "name": req.name,
                            "mimetype": req.mimetype,
                            "datas": req.attachment_data,
                            "description": req.content_id or "",
                            "content_id": req.content_id,
                            "checksum": checksum,
                        }
                    )

            if new_attachments:
                atts = self._repo.create_batch_with_tokens(
                    new_attachments, "maildesk.message_index", int(index_id)
                )

                for att in atts:
                    dtos.append(self._repo.build_dto_from_recordset(att))

            _logger.debug(
                "[AttachmentCacheService] Processed %d attachments (%d new, %d deduplicated)",
                len(to_materialize),
                len(new_attachments),
                deduplicated_count,
            )

        return dtos
