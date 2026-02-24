# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
AttachmentRepository: ir.attachment persistence layer.

Layer: infrastructure
"""

import logging
from typing import Any, Dict, List, Optional

from ..rendering.attachment_formatter import build_binary_attachment_dto
from ...application.services.attachment_cache_service import AttachmentDTO

_logger = logging.getLogger(__name__)


class AttachmentRepository:
    """Repository for ir.attachment persistence."""

    def __init__(self, env: Any):
        """
        Initialize repository.

        Args:
            env: Odoo environment or recordset with .env attribute
        """
        self._env = env.env if hasattr(env, "env") else env

    def find_by_checksums(
        self,
        checksums: List[str],
        *,
        res_model: Optional[str] = None,
        res_id: Optional[int] = None,
    ) -> Dict[str, int]:
        if not checksums:
            return {}

        Attachment = self._env["ir.attachment"].sudo()
        domain: List[Any] = [("checksum", "in", checksums)]
        if res_model:
            domain.append(("res_model", "=", str(res_model)))
        if res_id:
            domain.append(("res_id", "=", int(res_id)))
        existing = Attachment.search(domain)

        return {att.checksum: att.id for att in existing}

    def create_batch_with_tokens(
        self,
        batch_data: List[Dict[str, Any]],
        res_model: str,
        res_id: int,
    ) -> Any:
        if not batch_data:
            return self._env["ir.attachment"].sudo()

        Attachment = self._env["ir.attachment"].sudo()
        tokens = [Attachment._generate_access_token() for _ in batch_data]

        vals_list = []
        for i, data in enumerate(batch_data):
            vals = {
                "name": data["name"],
                "mimetype": data["mimetype"],
                "raw": data["datas"],
                "res_model": res_model,
                "res_id": res_id,
                "description": data.get("description", ""),
                "access_token": tokens[i],
            }

            if data.get("content_id"):
                vals["content_id"] = data["content_id"].strip().strip("<>").strip()

            vals_list.append(vals)

        atts = Attachment.with_context(
            force_db_storage=True,
            image_no_postprocess=True,
        ).create(vals_list)

        _logger.debug(
            "[AttachmentRepo] Batch created %d attachments",
            len(atts),
        )

        return atts

    def build_dto_from_recordset(self, att: Any) -> AttachmentDTO:
        info = build_binary_attachment_dto(att)

        return AttachmentDTO(
            id=info["id"],
            name=info["name"],
            mimetype=info["mimetype"],
            size=info["size"],
            access_token=info["access_token"],
            checksum=info.get("checksum", ""),
            content_id=info.get("content_id") or "",
            type=info["type"],
            extension=info["extension"],
            icon_mimetype=info["icon_mimetype"],
        )

    def ensure_token(self, attachment_id: int) -> str:
        att = self._env["ir.attachment"].sudo().browse(attachment_id)
        if not att.exists():
            raise ValueError(f"Attachment {attachment_id} does not exist")

        if not att.access_token:
            att.generate_access_token()

        return att.access_token

    def link_to_cache(self, attachment_id: int, cache_id: int) -> None:
        att = self._env["ir.attachment"].sudo().browse(attachment_id)
        if not att.exists():
            raise ValueError(f"Attachment {attachment_id} does not exist")

        att.write({"res_model": "maildesk.ui_cache", "res_id": cache_id})

    def build_dto_from_attachment(self, attachment_id: int) -> AttachmentDTO:
        att = self._env["ir.attachment"].sudo().browse(attachment_id)
        if not att.exists():
            raise ValueError(f"Attachment {attachment_id} does not exist")

        return self.build_dto_from_recordset(att)

    def create_with_token(
        self,
        name: str,
        mimetype: str,
        datas: bytes,
        res_model: str,
        res_id: int,
        description: Optional[str] = None,
    ) -> Any:
        batch_data = [
            {
                "name": name,
                "mimetype": mimetype,
                "datas": datas,
                "description": description,
                "content_id": description,
            }
        ]

        atts = self.create_batch_with_tokens(batch_data, res_model, res_id)
        return atts[0] if atts else None

    def get_by_id(self, attachment_id: int) -> Any:
        """
        Get ir.attachment record by ID.

        Args:
            attachment_id: ir.attachment ID

        Returns:
            ir.attachment record

        Raises:
            ValueError: If attachment does not exist
        """
        att = self._env["ir.attachment"].sudo().browse(attachment_id)
        if not att.exists():
            raise ValueError(f"Attachment {attachment_id} does not exist")
        return att

    def delete_by_cache_id(self, cache_id: int) -> None:
        """
        Delete all attachments linked to cache_id.

        Args:
            cache_id: maildesk.ui_cache ID
        """
        Attachment = self._env["ir.attachment"].sudo()
        atts = Attachment.search(
            [("res_model", "=", "maildesk.ui_cache"), ("res_id", "=", cache_id)]
        )

        if atts:
            _logger.info(
                "[AttachmentRepo] Deleting %d attachments for cache %d",
                len(atts),
                cache_id,
            )
            atts.unlink()
