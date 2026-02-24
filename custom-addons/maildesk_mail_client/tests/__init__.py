# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk test suite.

Registers the `maildesk_mail_client` automated test suite for Odoo.
Layer: tests.
"""

from . import test_model_mailbox_account  # noqa: F401
from . import test_model_mailbox_folder  # noqa: F401
from . import test_model_mailbox_sync  # noqa: F401
from . import test_fetchmail_confirm_login_graph_bypass  # noqa: F401
from . import test_sync_orchestrator_respects_backoff  # noqa: F401
from . import test_use_case_backfill_folder_progressive  # noqa: F401
from . import test_use_case_backfill_folder_progressive_gmail  # noqa: F401
from . import test_use_case_backfill_folder_progressive_outlook  # noqa: F401
from . import test_use_case_bootstrap_folder  # noqa: F401
from . import test_use_case_bootstrap_folder_gmail  # noqa: F401
from . import test_use_case_bootstrap_folder_outlook  # noqa: F401
from . import test_use_case_drafts  # noqa: F401
from . import test_use_case_ingest_queue  # noqa: F401
from . import test_use_case_list_messages_ssot  # noqa: F401
from . import test_use_case_open_linked_document  # noqa: F401
from . import test_use_case_open_message  # noqa: F401
from . import test_attachment_model_unified  # noqa: F401
from . import test_use_case_partner_actions  # noqa: F401
from . import test_use_case_prepare_reply_forward  # noqa: F401
from . import test_use_case_sanitize_message_body  # noqa: F401
from . import test_use_case_scan_imap_folders  # noqa: F401
from . import test_use_case_send_email  # noqa: F401
from . import test_use_case_sync_gmail_incremental_and_history  # noqa: F401
from . import test_use_case_sync_imap_folder  # noqa: F401
from . import test_use_case_sync_outlook_delta  # noqa: F401
from . import test_ssot_outgoing_delivery_reconciliation  # noqa: F401
from . import test_use_case_threading  # noqa: F401
from . import test_use_case_ui_actions  # noqa: F401
from . import test_mailbox_folder_utf7  # noqa: F401
from . import test_mail_thread_cc_bcc_recipients_schema  # noqa: F401
from . import test_imap_encoding_safe_folder_operation  # noqa: F401
from . import test_gmail_label_resolver_localized  # noqa: F401
from . import test_sender_identity_content_trusted  # noqa: F401
from . import test_security_access  # noqa: F401
from . import test_mail_list_direction_filters  # noqa: F401
from . import test_partner_filter_company_domain  # noqa: F401
