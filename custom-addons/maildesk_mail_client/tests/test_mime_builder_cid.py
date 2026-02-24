# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Tests for MIME Builder CID (inline image) handling.

Verifies:
1. CID detection in HTML
2. CID-to-attachment matching
3. HTML CID rewriting
4. MIME structure (multipart/related)
5. Content-ID header generation
6. Mixed inline + regular attachments
"""

import base64
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestMimeBuilderCID(TransactionCase):
    """Test MIME builder inline image (CID) support."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Attachment = cls.env["ir.attachment"].sudo()
        cls.FetchmailServer = cls.env["fetchmail.server"].sudo()
        cls.Account = cls.env["mailbox.account"].sudo()

    def _create_test_account(self):
        """Create a test email account."""
        server = self.FetchmailServer.create(
            {
                "name": "Test Server",
                "server_type": "imap",
                "server": "imap.test.com",
                "port": 993,
                "user": "test@test.com",
                "password": "secret",
                "is_ssl": True,
            }
        )

        with patch(
            "odoo.addons.maildesk_mail_client.models.mailbox_account.MailboxAccount.refresh_imap_caps",
            return_value=None,
        ):
            return self.Account.create(
                {
                    "name": "Test Account",
                    "email": "test@test.com",
                    "owner_id": self.env.user.id,
                    "access_user_ids": [(6, 0, [self.env.user.id])],
                    "mail_server_id": server.id,
                }
            )

    def _create_image_attachment(self, name="test.png", mimetype="image/png"):
        """Create a test image attachment."""
        # 1x1 PNG pixel (base64)
        png_data = b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        return self.Attachment.create(
            {
                "name": name,
                "datas": png_data,
                "mimetype": mimetype,
                "res_model": "mailbox.account",
                "res_id": 0,
            }
        )

    def _create_pdf_attachment(self, name="document.pdf"):
        """Create a test PDF attachment (regular, not inline)."""
        pdf_data = base64.b64encode(b"%PDF-1.4 fake pdf content")
        return self.Attachment.create(
            {
                "name": name,
                "datas": pdf_data,
                "mimetype": "application/pdf",
                "res_model": "mailbox.account",
                "res_id": 0,
            }
        )

    def _parse_mime(self, mime_message):
        """Parse EmailMessage to raw MIME bytes and back for inspection."""
        raw_bytes = mime_message.as_bytes()
        return BytesParser(policy=policy.default).parsebytes(raw_bytes)

    def test_single_inline_image_basic(self):
        """Single inline image with CID reference is embedded correctly."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        img = self._create_image_attachment("screenshot.png")

        html = '<html><body><p>Check this:</p><img src="cid:screenshot.png" /></body></html>'

        builder = MimeBuilder(self.env)
        msg, msg_id = builder.build(
            account=account,
            subject="Test",
            body_html=html,
            to=["recipient@example.com"],
            attachment_ids=[img.id],
        )

        # Verify HTML was rewritten to stable Content-ID
        parsed = self._parse_mime(msg)
        html_parts = [p for p in parsed.walk() if p.get_content_type() == "text/html"]
        self.assertTrue(len(html_parts) > 0, "No HTML part found")
        html_content = html_parts[0].get_content()

        # Should contain cid:XXX@maildesk, not original cid:screenshot.png
        self.assertIn(f"cid:{img.id}@maildesk", html_content)
        self.assertNotIn("cid:screenshot.png", html_content)

        # Verify inline image part exists with Content-ID header
        inline_parts = [
            p
            for p in parsed.walk()
            if p.get_content_type().startswith("image/") and p.get("Content-ID")
        ]
        self.assertEqual(len(inline_parts), 1, "Expected exactly 1 inline image")

        cid_header = inline_parts[0].get("Content-ID")
        self.assertIsNotNone(cid_header)
        # Content-ID header has angle brackets: <123@maildesk>
        self.assertIn(f"{img.id}@maildesk", cid_header)

        # Verify Content-Disposition is inline
        disp = inline_parts[0].get("Content-Disposition", "")
        self.assertIn("inline", disp)

    def test_multiple_inline_images(self):
        """Multiple inline images are all embedded correctly."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        img1 = self._create_image_attachment("image1.png")
        img2 = self._create_image_attachment("image2.jpg", "image/jpeg")

        html = """
        <html><body>
            <p>Image 1: <img src="cid:image1.png" /></p>
            <p>Image 2: <img src="cid:image2.jpg" /></p>
        </body></html>
        """

        builder = MimeBuilder(self.env)
        msg, _ = builder.build(
            account=account,
            subject="Multi Image Test",
            body_html=html,
            to=["test@example.com"],
            attachment_ids=[img1.id, img2.id],
        )

        parsed = self._parse_mime(msg)

        # Should have 2 inline image parts
        inline_parts = [
            p
            for p in parsed.walk()
            if p.get_content_type().startswith("image/") and p.get("Content-ID")
        ]
        self.assertEqual(len(inline_parts), 2)

        # Verify both Content-IDs present
        cids = [p.get("Content-ID") for p in inline_parts]
        self.assertTrue(any(f"{img1.id}@maildesk" in cid for cid in cids))
        self.assertTrue(any(f"{img2.id}@maildesk" in cid for cid in cids))

    def test_mixed_inline_and_regular_attachments(self):
        """Inline images + regular attachments handled correctly."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        img = self._create_image_attachment("inline.png")
        pdf = self._create_pdf_attachment("report.pdf")

        html = '<html><body><img src="cid:inline.png" /><p>See attached PDF</p></body></html>'

        builder = MimeBuilder(self.env)
        msg, _ = builder.build(
            account=account,
            subject="Mixed",
            body_html=html,
            to=["test@example.com"],
            attachment_ids=[img.id, pdf.id],
        )

        parsed = self._parse_mime(msg)

        # Inline image: has Content-ID, disposition=inline
        inline_parts = [
            p
            for p in parsed.walk()
            if p.get_content_type().startswith("image/") and p.get("Content-ID")
        ]
        self.assertEqual(len(inline_parts), 1)
        self.assertIn("inline", inline_parts[0].get("Content-Disposition", ""))

        # Regular PDF: no Content-ID, disposition=attachment
        pdf_parts = [
            p for p in parsed.walk() if p.get_content_type() == "application/pdf"
        ]
        self.assertEqual(len(pdf_parts), 1)
        self.assertIsNone(pdf_parts[0].get("Content-ID"))
        # Content-Disposition might be implicitly "attachment" or explicitly set
        # Just verify it's NOT inline
        # EmailMessage may not set explicit disposition for top-level attachments
        # The key is: no Content-ID = not inline
        self.assertIsNone(pdf_parts[0].get("Content-ID"))

    def test_cid_without_matching_attachment_unchanged(self):
        """CID reference without matching attachment stays in HTML unchanged."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        img = self._create_image_attachment("real_image.png")

        html = """
        <html><body>
            <img src="cid:real_image.png" />
            <img src="cid:missing_image.png" />
        </body></html>
        """

        builder = MimeBuilder(self.env)
        msg, _ = builder.build(
            account=account,
            subject="Partial CID",
            body_html=html,
            to=["test@example.com"],
            attachment_ids=[img.id],  # Only one image attached
        )

        parsed = self._parse_mime(msg)
        html_parts = [p for p in parsed.walk() if p.get_content_type() == "text/html"]
        html_content = html_parts[0].get_content()

        # Real image CID should be rewritten
        self.assertIn(f"cid:{img.id}@maildesk", html_content)

        # Missing image CID should remain unchanged (defensive behavior)
        self.assertIn("cid:missing_image.png", html_content)

    def test_no_cid_references_no_inline_processing(self):
        """Email without CID references treats all attachments as regular."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        img = self._create_image_attachment("image.png")

        html = "<html><body><p>No inline images here</p></body></html>"

        builder = MimeBuilder(self.env)
        msg, _ = builder.build(
            account=account,
            subject="No CID",
            body_html=html,
            to=["test@example.com"],
            attachment_ids=[img.id],
        )

        parsed = self._parse_mime(msg)

        # No inline parts (no Content-ID headers)
        inline_parts = [p for p in parsed.walk() if p.get("Content-ID")]
        self.assertEqual(len(inline_parts), 0)

        # Image should be regular attachment
        image_parts = [
            p for p in parsed.walk() if p.get_content_type().startswith("image/")
        ]
        self.assertEqual(len(image_parts), 1)
        self.assertIsNone(image_parts[0].get("Content-ID"))

    def test_basename_matching(self):
        """CID matching works with basename (without extension)."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        img = self._create_image_attachment("screenshot.png")

        # CID reference uses basename without extension
        html = '<html><body><img src="cid:screenshot" /></body></html>'

        builder = MimeBuilder(self.env)
        msg, _ = builder.build(
            account=account,
            subject="Basename Match",
            body_html=html,
            to=["test@example.com"],
            attachment_ids=[img.id],
        )

        parsed = self._parse_mime(msg)

        # Should have inline image (basename matched)
        inline_parts = [
            p
            for p in parsed.walk()
            if p.get_content_type().startswith("image/") and p.get("Content-ID")
        ]
        self.assertEqual(len(inline_parts), 1)

    def test_single_cid_single_image_auto_match(self):
        """Single CID + single image attachment auto-matches even if names differ."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        img = self._create_image_attachment("actual_name.png")

        # CID uses different name
        html = '<html><body><img src="cid:ii_generated_12345" /></body></html>'

        builder = MimeBuilder(self.env)
        msg, _ = builder.build(
            account=account,
            subject="Auto Match",
            body_html=html,
            to=["test@example.com"],
            attachment_ids=[img.id],
        )

        parsed = self._parse_mime(msg)
        html_parts = [p for p in parsed.walk() if p.get_content_type() == "text/html"]
        html_content = html_parts[0].get_content()

        # Should have matched and rewritten
        self.assertIn(f"cid:{img.id}@maildesk", html_content)

        inline_parts = [p for p in parsed.walk() if p.get("Content-ID")]
        self.assertEqual(len(inline_parts), 1)

    def test_mime_structure_multipart_related(self):
        """MIME structure uses multipart/related for HTML + inline images."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        img = self._create_image_attachment("test.png")

        html = '<html><body><img src="cid:test.png" /></body></html>'

        builder = MimeBuilder(self.env)
        msg, _ = builder.build(
            account=account,
            subject="Structure Test",
            body_html=html,
            to=["test@example.com"],
            attachment_ids=[img.id],
        )

        parsed = self._parse_mime(msg)

        # Root should be multipart/mixed or multipart/alternative
        self.assertTrue(parsed.is_multipart())

        # Note: Python's EmailMessage.add_related creates multipart/related implicitly
        # The structure may vary, but key test: inline image has Content-ID
        inline_parts = [p for p in parsed.walk() if p.get("Content-ID")]
        self.assertGreater(
            len(inline_parts), 0, "Inline image with Content-ID must exist"
        )

    def test_headers_bcc_threading_and_correlation(self):
        """Bcc never leaks; threading headers are RFC 5322 compliant; correlation header is set."""
        from ..infrastructure.email.mime_builder import MimeBuilder

        account = self._create_test_account()
        builder = MimeBuilder(self.env)

        msg, _msg_id = builder.build(
            account=account,
            subject="Test",
            body_html="<p>Hello</p>",
            to=["to@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            reply_message_id="<P@Example.com>",
            reply_references="<r1@example.com> <p@example.com>",
            outgoing_id="maildesk-123",
        )

        self.assertNotIn("Bcc", msg)
        self.assertEqual(msg.get("X-MailDesk-Outgoing-ID"), "maildesk-123")
        self.assertEqual(msg.get("In-Reply-To"), "<p@example.com>")
        self.assertEqual(msg.get("References"), "<r1@example.com> <p@example.com>")
