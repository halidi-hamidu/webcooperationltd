# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/18.0/legal/licenses/licenses.html#odoo-proprietary-license

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from ..infrastructure.utils.imap_encoding import safe_folder_operation


@tagged("post_install", "-at_install")
class TestSafeFolderOperation(TransactionCase):
    """Validate that IMAP folder error logging never crashes on encoding."""

    def test_safe_folder_operation_handles_unencodable_folder_names(self):
        folder_name = "Broken\ud800Name"  # unpaired surrogate

        def op():
            raise RuntimeError("boom")

        with mute_logger(
            "odoo.addons.maildesk_mail_client.infrastructure.utils.imap_encoding"
        ):
            res = safe_folder_operation("STATUS", folder_name, op)
        self.assertIsNone(res)

    def test_safe_folder_operation_handles_bytes_folder_names(self):
        folder_name = b"\xff\xfe"

        def op():
            raise RuntimeError("boom")

        with mute_logger(
            "odoo.addons.maildesk_mail_client.infrastructure.utils.imap_encoding"
        ):
            res = safe_folder_operation("SELECT", folder_name, op)
        self.assertIsNone(res)
