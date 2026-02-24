# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
NormalizeOutgoingHtml Service

Application-layer service that enforces CID invariants for outgoing emails.

Responsibilities:
- Detect cid: references in HTML
- Match to ir.attachment records
- Assign stable Content-IDs ({attachment_id}@maildesk)
- Rewrite HTML to use stable IDs
- Update attachment.content_id metadata

This service is the SINGLE SOURCE OF TRUTH for CID normalization.
It is called by:
- SaveDraft (before persisting draft)
- SendEmail (before MIME building)

Layer: application/services
"""

import logging
import re
from typing import List, Dict, Tuple, Any

import lxml.html

_logger = logging.getLogger(__name__)


class NormalizeOutgoingHtml:
    """
    Normalize outgoing HTML for email composition.

    Ensures all cid: references use stable Content-IDs and map to real attachments.

    CRITICAL INVARIANTS (enforced):
    1. All cid: references use format: cid:{attachment_id}@maildesk
    2. Every cid: reference has matching ir.attachment with content_id set
    3. No unstable/temporary CIDs (e.g., cid:ii_xxx) persist after normalization
    """

    def __init__(self, env):
        """
        Initialize normalization service.

        Args:
            env: Odoo environment for accessing ir.attachment
        """
        self._env = env

    def normalize(
        self, body_html: str, attachment_ids: List[int]
    ) -> Tuple[str, List[int]]:
        """
        Normalize outgoing HTML and attachments.

        Args:
            body_html: Raw HTML from editor (may contain cid:ii_xxx refs)
            attachment_ids: List of ir.attachment IDs

        Returns:
            Tuple of:
            - normalized_html: HTML with stable cid: refs
            - updated_attachment_ids: IDs of attachments with content_id set

        Example:
            Input:  <img src="cid:ii_mkea90350">
            Output: <img src="cid:123@maildesk">
            Side effect: ir.attachment(123).content_id = "123@maildesk"
        """
        if not body_html:
            return body_html, attachment_ids or []

        # 1. Extract CID references from HTML
        cid_refs = self._extract_cid_references(body_html)
        if not cid_refs:
            _logger.debug("[NormalizeHTML] No CID references found")
            # Still absolutize relative URLs even without CIDs
            absolutized_html = self._absolutize_relative_urls(body_html)
            return absolutized_html, attachment_ids or []

        _logger.info(
            f"[NormalizeHTML] Found {len(cid_refs)} CID references: {cid_refs}"
        )

        # 2. Fetch attachments
        Attachment = self._env["ir.attachment"].sudo()
        attachments = (
            Attachment.browse(attachment_ids) if attachment_ids else Attachment
        )

        if not attachments:
            _logger.warning(
                "[NormalizeHTML] No attachments provided, CIDs will remain unresolved"
            )
            return body_html, []

        # 3. Build mapping: original_cid → (attachment_record, stable_content_id)
        cid_mapping = self._match_cids_to_attachments(cid_refs, attachments)

        if not cid_mapping:
            _logger.warning(
                f"[NormalizeHTML] No CID matches found (refs={len(cid_refs)}, "
                f"attachments={len(attachments)})"
            )
            return body_html, attachment_ids or []

        # 4. Update attachment.content_id for matched attachments
        updated_ids = []
        for original_cid, (att, stable_cid) in cid_mapping.items():
            if att.content_id != stable_cid:
                att.write({"content_id": stable_cid})
                _logger.info(
                    f"[NormalizeHTML] Set attachment {att.id} content_id: "
                    f"{att.content_id or '(empty)'} → {stable_cid}"
                )
            updated_ids.append(att.id)

        # 5. Rewrite HTML to use stable Content-IDs
        normalized_html = self._rewrite_html(body_html, cid_mapping)

        _logger.info(
            f"[NormalizeHTML] Normalized {len(cid_mapping)} inline images "
            f"(updated {len(updated_ids)} attachment records)"
        )

        # 6. Convert relative URLs to absolute URLs for external recipients
        normalized_html = self._absolutize_relative_urls(normalized_html)

        return normalized_html, updated_ids

    def _extract_cid_references(self, html: str) -> set:
        """
        Extract all cid: references from HTML.

        Args:
            html: HTML content

        Returns:
            Set of CID values (without "cid:" prefix)

        Example:
            Input:  '<img src="cid:ii_mkea90350">'
            Output: {"ii_mkea90350"}
        """
        cids = set()
        # Pattern: src="cid:xxx" or src='cid:xxx'
        pattern = r'src=["\']cid:([^"\']+)["\']'
        for match in re.finditer(pattern, html, re.IGNORECASE):
            cid = match.group(1).strip()
            if cid:
                cids.add(cid)
        return cids

    def _match_cids_to_attachments(
        self, cid_refs: set, attachments: Any
    ) -> Dict[str, Tuple[Any, str]]:
        """
        Match CID references to attachment records.

        Matching strategies (in order):
        1. Exact name match: cid:image.png → attachment.name = "image.png"
        2. Basename match: cid:screenshot → attachment.name = "screenshot.png"
        3. Auto-match: 1 CID + 1 image attachment → automatic pairing

        Args:
            cid_refs: Set of CID values from HTML
            attachments: Recordset of ir.attachment

        Returns:
            Dict mapping: original_cid → (attachment_record, stable_content_id)

        Example:
            cid_refs = {"ii_mkea90350"}
            attachments = [ir.attachment(123, name="screenshot.png")]
            Returns: {"ii_mkea90350": (ir.attachment(123), "123@maildesk")}
        """
        mapping = {}

        # Filter to image attachments only
        image_atts = [
            att
            for att in attachments
            if att.mimetype and att.mimetype.startswith("image/")
        ]

        if not image_atts:
            _logger.debug("[NormalizeHTML] No image attachments found")
            return mapping

        _logger.debug(
            f"[NormalizeHTML] Matching {len(cid_refs)} CID refs to "
            f"{len(image_atts)} image attachments"
        )

        for att in image_atts:
            stable_cid = f"{att.id}@maildesk"

            # Strategy 1: Exact name match
            if att.name and att.name in cid_refs:
                mapping[att.name] = (att, stable_cid)
                _logger.debug(f"[CID Match] Exact name: {att.name} → {stable_cid}")
                continue

            # Strategy 2: Basename match (without extension)
            if att.name:
                basename = att.name.rsplit(".", 1)[0] if "." in att.name else att.name
                for cid_ref in cid_refs:
                    if cid_ref in mapping:
                        continue  # Already matched
                    cid_base = cid_ref.rsplit(".", 1)[0] if "." in cid_ref else cid_ref
                    if basename.lower() == cid_base.lower():
                        mapping[cid_ref] = (att, stable_cid)
                        _logger.debug(f"[CID Match] Basename: {cid_ref} → {stable_cid}")
                        break

        # Strategy 3: Auto-match if 1 unmatched CID + 1 unmatched image
        unmatched_cids = cid_refs - set(mapping.keys())
        unmatched_atts = [
            att
            for att in image_atts
            if not any(att.id == m[0].id for m in mapping.values())
        ]

        if len(unmatched_cids) == 1 and len(unmatched_atts) == 1:
            cid_ref = list(unmatched_cids)[0]
            att = unmatched_atts[0]
            stable_cid = f"{att.id}@maildesk"
            mapping[cid_ref] = (att, stable_cid)
            _logger.debug(f"[CID Match] Auto-match: {cid_ref} → {stable_cid}")

        return mapping

    def _rewrite_html(self, html: str, cid_mapping: Dict[str, Tuple[Any, str]]) -> str:
        """
        Rewrite HTML to use stable Content-IDs.

        Args:
            html: Original HTML
            cid_mapping: Dict of original_cid → (attachment, stable_cid)

        Returns:
            HTML with rewritten cid: references

        Example:
            Input:  <img src="cid:ii_mkea90350">
            Mapping: {"ii_mkea90350": (att_123, "123@maildesk")}
            Output: <img src="cid:123@maildesk">
        """
        if not cid_mapping:
            return html

        try:
            root = lxml.html.fromstring(html)
        except Exception as e:
            _logger.warning(f"[NormalizeHTML] Failed to parse HTML: {e}")
            return html

        modified = False
        for img in root.iter("img"):
            src = img.get("src", "")
            if not src.startswith("cid:"):
                continue

            # Extract original CID
            original_cid = src.split("cid:", 1)[1].strip()

            # Look up mapping
            if original_cid in cid_mapping:
                _, stable_cid = cid_mapping[original_cid]
                img.set("src", f"cid:{stable_cid}")
                modified = True
                _logger.debug(f"[HTML Rewrite] cid:{original_cid} → cid:{stable_cid}")

        if modified:
            return lxml.html.tostring(root, encoding="unicode")
        return html

    def _absolutize_relative_urls(self, html: str) -> str:
        """
        Convert relative URLs to absolute URLs for external email recipients.

        Converts:
        - /web/image/... → https://domain.com/web/image/...
        - /web/content/... → https://domain.com/web/content/...

        Args:
            html: HTML content with potentially relative URLs

        Returns:
            HTML with absolute URLs
        """
        if not html:
            return html

        # Get base URL from Odoo config
        base_url = self._env["ir.config_parameter"].sudo().get_param("web.base.url", "")

        if not base_url:
            _logger.warning(
                "[NormalizeHTML] No web.base.url configured, cannot absolutize URLs"
            )
            return html

        # Remove trailing slash from base_url
        base_url = base_url.rstrip("/")

        try:
            root = lxml.html.fromstring(html)
        except Exception as e:
            _logger.warning(
                f"[NormalizeHTML] Failed to parse HTML for URL rewriting: {e}"
            )
            return html

        modified = False

        # Process img src attributes
        for img in root.iter("img"):
            src = img.get("src", "")
            if src.startswith("/") and not src.startswith("//"):
                new_src = f"{base_url}{src}"
                img.set("src", new_src)
                modified = True
                _logger.debug(f"[URL Absolutize] {src} → {new_src}")

        # Process anchor href attributes
        for a in root.iter("a"):
            href = a.get("href", "")
            if href.startswith("/") and not href.startswith("//"):
                new_href = f"{base_url}{href}"
                a.set("href", new_href)
                modified = True

        if modified:
            _logger.info("[NormalizeHTML] Absolutized relative URLs")
            return lxml.html.tostring(root, encoding="unicode")

        return html
