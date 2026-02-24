# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Attachment formatter: DTO building for attachments.

Layer: infrastructure
"""

import logging

_logger = logging.getLogger(__name__)

VIEWABLE_MIMETYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "application/pdf",
}

MIME_TO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
    "application/javascript": "js",
    "text/x-python": "py",
    "application/zip": "zip",
    "application/x-rar-compressed": "rar",
    "video/mp4": "mp4",
    "audio/mpeg": "mp3",
    "text/csv": "csv",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/html": "html",
    "application/json": "json",
}

EXT_TO_MIME = {
    "psd": "image/vnd.adobe.photoshop",
    "zip": "application/zip",
    "rar": "application/x-rar-compressed",
    "mp4": "video/mp4",
    "mp3": "audio/mpeg",
    "csv": "text/csv",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "html": "text/html",
    "json": "application/json",
    "js": "application/javascript",
    "py": "text/x-python",
    "pdf": "application/pdf",
}


def attachment_common_info(name: str, mime: str) -> dict:
    """
    Generate common attachment metadata.

    Args:
        name: Filename
        mime: MIME type

    Returns:
        Dict with extension, icon_mimetype, isImage, isPdf, isViewable
    """
    ext = (name or "").rsplit(".", 1)[-1].lower() if "." in (name or "") else ""
    icon_mime = mime or "application/octet-stream"

    if not ext and mime:
        ext = MIME_TO_EXT.get(mime, "")

    if not mime or mime == "application/octet-stream":
        icon_mime = EXT_TO_MIME.get(ext, "application/octet-stream")

    return {
        "extension": ext,
        "icon_mimetype": icon_mime,
        "isImage": icon_mime.startswith("image/") and icon_mime in VIEWABLE_MIMETYPES,
        "isPdf": icon_mime == "application/pdf",
        "isViewable": icon_mime in VIEWABLE_MIMETYPES,
    }


def build_binary_attachment_dto(att_record) -> dict:
    """
    Build attachment DTO for ir.attachment record.

    Follows Odoo FileModel contract - sends only data fields,
    FileModel computes URLs and type booleans.

    Args:
        att_record: ir.attachment ORM record

    Returns:
        Dict matching Odoo FileModel expectations
    """
    token = att_record.access_token or ""
    if not token:
        _logger.warning(
            "[build_binary_attachment_dto] Attachment %d missing access_token",
            att_record.id,
        )

    content_id = ""
    try:
        content_id = (getattr(att_record, "content_id", None) or "").strip("<>").strip()
    except Exception:
        content_id = ""
    if not content_id:
        content_id = (
            (getattr(att_record, "description", None) or "").strip("<>").strip()
        )
    name = att_record.name
    mimetype = att_record.mimetype
    common = attachment_common_info(name, mimetype)

    return {
        "id": att_record.id,
        "name": name,
        "filename": name,
        "mimetype": mimetype,
        "extension": common.get("extension", ""),
        "size": att_record.file_size or 0,
        "type": "binary",
        "checksum": att_record.checksum or "",
        "access_token": token,
        "res_name": att_record.res_name or name,
        "content_id": content_id,
        "contentId": content_id,
        "icon_mimetype": common.get("icon_mimetype", "application/octet-stream"),
    }
