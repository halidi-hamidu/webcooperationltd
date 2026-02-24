# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

"""Tests for `infrastructure/rendering/preview_extractor.py`.

These tests validate preview extraction under real-world IMAP payload variants:
- quoted-printable UTF-8 artifacts (e.g. '=C3=BC') must be decoded to Unicode.
- HTML previews must not include <style> blocks (CSS must not appear as text).
"""

from __future__ import annotations

from odoo.tests.common import TransactionCase

from ..infrastructure.rendering.preview_extractor import extract_imap_preview


class TestPreviewExtractorMime(TransactionCase):
    """Validate MIME-aware preview extraction."""

    def test_quoted_printable_utf8_is_decoded(self):
        """Quoted-printable bodies must be decoded to real Unicode characters."""
        raw = (
            b"Subject: Test\r\n"
            b"Content-Type: text/plain; charset=UTF-8\r\n"
            b"Content-Transfer-Encoding: quoted-printable\r\n"
            b"\r\n"
            b"Mit freundlichen Gr=C3=BC=C3=9Fen\r\n"
        )
        preview = extract_imap_preview(raw, "fallback")
        self.assertIn("Grüßen", preview)

    def test_html_preview_strips_style_blocks(self):
        """HTML previews must not leak CSS from <style> tags into plain text."""
        raw = (
            b"Subject: Test\r\n"
            b"Content-Type: text/html; charset=UTF-8\r\n"
            b"\r\n"
            b"<html><head><style>body{color:red}</style></head>"
            b"<body>Hello <b>World</b></body></html>"
        )
        preview = extract_imap_preview(raw, "fallback")
        self.assertIn("Hello World", preview)
        self.assertNotIn("body{color:red}", preview)

    def test_fallback_decodes_quoted_printable_without_headers(self):
        """Fragments without MIME headers should still decode common QP artifacts."""
        raw = b"Hallo Gr=C3=BC=C3=9Fe"
        preview = extract_imap_preview(raw, "fallback")
        self.assertIn("Grüße", preview)

    def test_fallback_does_not_render_base64_gibberish(self):
        """Fragments that look like base64 must not be shown as preview text."""
        raw = b"R3V0ZW4gTW9yZ2Vu" * 10  # base64-like payload without headers
        preview = extract_imap_preview(raw, "fallback")
        self.assertEqual(preview, "fallback")

    def test_rfc822_headers_are_not_used_as_preview(self):
        """Header-only RFC822 slices must fall back to subject, not show headers."""
        raw = (
            b"Return-Path: <bounce@example.com>\r\n"
            b"Delivered-To: info@example.com\r\n"
            b"Received: from mail.example.com by mx.example.com\r\n"
            b"\r\n"
        )
        preview = extract_imap_preview(raw, "fallback")
        self.assertEqual(preview, "fallback")

    def test_rfc822_preview_prefers_body_over_headers(self):
        """RFC822 slices must extract preview from body, never from headers."""
        raw = (
            b"Return-Path: <bounce@example.com>\r\n"
            b"Subject: Hello\r\n"
            b"\r\n"
            b"Body line 1\r\n"
        )
        preview = extract_imap_preview(raw, "fallback")
        self.assertIn("Body line 1", preview)
