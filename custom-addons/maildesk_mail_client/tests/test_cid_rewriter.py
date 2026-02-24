# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Tests for CID rewriter (cid_rewriter.py).

Verifies Odoo mail_thread.py pattern:
1. CID that matches attachment → /web/image/{id}?access_token=...
2. CID that does NOT match → remains cid:... (body intact)
"""

from ..infrastructure.rendering.cid_rewriter import replace_cid_src


class TestCidRewriter:
    """Test CID replacement following Odoo pattern."""

    def test_cid_replaced_when_attachment_matches(self):
        """CID is replaced when attachment with id and token exists."""
        body_html = '<html><body><img src="cid:image001@example.com"/></body></html>'
        attachments = [
            {
                "id": 123,
                "access_token": "abc123token",
                "content_id": "image001@example.com",
            }
        ]

        result = replace_cid_src(body_html, attachments)

        assert 'src="/web/image/123?access_token=abc123token"' in result
        assert "cid:" not in result

    def test_cid_unchanged_when_no_matching_attachment(self):
        """CID remains unchanged when no matching attachment exists."""
        body_html = '<html><body><img src="cid:unknown@example.com"/></body></html>'
        attachments = [
            {
                "id": 123,
                "access_token": "abc123token",
                "content_id": "different@example.com",
            }
        ]

        result = replace_cid_src(body_html, attachments)

        # CID MUST remain unchanged (Odoo pattern - never blank)
        assert 'src="cid:unknown@example.com"' in result

    def test_cid_unchanged_when_no_attachments(self):
        """CID remains unchanged when attachments list is empty."""
        body_html = '<html><body><img src="cid:image001@example.com"/></body></html>'
        attachments = []

        result = replace_cid_src(body_html, attachments)

        # CID MUST remain unchanged
        assert 'src="cid:image001@example.com"' in result

    def test_cid_unchanged_when_token_missing(self):
        """CID remains unchanged when attachment has no token."""
        body_html = '<html><body><img src="cid:image001@example.com"/></body></html>'
        attachments = [
            {
                "id": 123,
                "access_token": "",  # No token
                "content_id": "image001@example.com",
            }
        ]

        result = replace_cid_src(body_html, attachments)

        # CID MUST remain unchanged (no token = no replacement)
        assert 'src="cid:image001@example.com"' in result

    def test_cid_unchanged_when_id_missing(self):
        """CID remains unchanged when attachment has no id."""
        body_html = '<html><body><img src="cid:image001@example.com"/></body></html>'
        attachments = [
            {
                "id": None,  # No ID
                "access_token": "abc123token",
                "content_id": "image001@example.com",
            }
        ]

        result = replace_cid_src(body_html, attachments)

        # CID MUST remain unchanged
        assert 'src="cid:image001@example.com"' in result

    def test_multiple_cids_partial_replacement(self):
        """Only matching CIDs are replaced, others remain unchanged."""
        body_html = """<html><body>
            <img src="cid:found@example.com"/>
            <img src="cid:notfound@example.com"/>
        </body></html>"""
        attachments = [
            {
                "id": 100,
                "access_token": "token100",
                "content_id": "found@example.com",
            }
        ]

        result = replace_cid_src(body_html, attachments)

        # First CID replaced
        assert 'src="/web/image/100?access_token=token100"' in result
        # Second CID unchanged (NOT removed, NOT empty)
        assert 'src="cid:notfound@example.com"' in result

    def test_cid_with_angle_brackets(self):
        """CID matching works with angle brackets in content_id."""
        body_html = '<html><body><img src="cid:image001@example.com"/></body></html>'
        attachments = [
            {
                "id": 123,
                "access_token": "abc123token",
                "content_id": "<image001@example.com>",  # With angle brackets
            }
        ]

        result = replace_cid_src(body_html, attachments)

        assert 'src="/web/image/123?access_token=abc123token"' in result

    def test_non_cid_images_unchanged(self):
        """Images with non-cid src are not modified."""
        body_html = '<html><body><img src="https://example.com/img.png"/></body></html>'
        attachments = [
            {
                "id": 123,
                "access_token": "abc123token",
                "content_id": "image001@example.com",
            }
        ]

        result = replace_cid_src(body_html, attachments)

        assert 'src="https://example.com/img.png"' in result

    def test_empty_body_returns_empty(self):
        """Empty body returns empty string."""
        result = replace_cid_src(
            "", [{"id": 1, "access_token": "x", "content_id": "y"}]
        )
        assert result == ""

    def test_none_body_returns_none(self):
        """None body returns None."""
        result = replace_cid_src(
            None, [{"id": 1, "access_token": "x", "content_id": "y"}]
        )
        assert result is None
