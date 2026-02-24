# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

# ruff: noqa: F401

"""MailDesk Init.

Exports subpackages to register MailDesk components in Odoo.
Layer: odoo models.
"""

from . import (
    fetchmail_server,
    ir_attachment,
    ir_websocket,
    ir_mail_server,
    mail_mail,
    mail_message,
    mail_message_tag,
    mail_thread,
    mailbox_account,
    mailbox_folder,
    mailbox_sync,
    maildesk_draft,
    maildesk_account_lease,
    maildesk_email_state,
    maildesk_ui_presence,
    ingest_queue,
    maildesk_ui_cache,
    message_index,
    orchestration,
    res_config_settings,
    res_partner,
)
