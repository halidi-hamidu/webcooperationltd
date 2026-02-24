# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

{
    "name": "Email Client & Unified Inbox for Odoo – MailDesk Basic",
    "version": "19.0.3.1.7",
    "summary": "Odoo unified inbox & email client for Gmail/Google Workspace, Outlook/Microsoft 365 (Exchange Online), and IMAP (OAuth2, background sync). Tags, threading, shared inbox, partner linking – full email management in Odoo.",
    "description": """
        MailDesk Basic – Unified Email Client for Odoo

        MailDesk Basic is a fast and reliable email client fully integrated into Odoo.
        It supports Gmail, Outlook, Mailcow and nearly all modern IMAP servers, with real-time one-way synchronization of incoming messages.

        Key Features:
        - Unified inbox for multiple mail accounts (Gmail, Outlook, IMAP)
        - Deterministic background sync for Gmail and IMAP
        - Full HTML email composer with drag, resize, and attachments
        - Threaded message view (conversation mode)
        - Draft autosave and restore
        - Folder management (Inbox, Sent, Archive, Trash)
        - Actions: reply, forward, archive, delete (local)
        - Manual tagging system for organizing messages
        - Partner (contact) detection and linking
        - Clean OWL-based user interface

        Designed to centralize communication and replace external email clients – fully inside Odoo.

        Compatible with:
        - Gmail (OAuth2)
        - Microsoft Outlook / Office365 (OAuth2)
        - Mailcow, Zimbra, Dovecot, cPanel and most modern IMAP servers

        Developed and supported by Metzler IT GmbH – Odoo Experts from Germany.
    """,
    "live_test_url": "https://mit-odoo.com/module/maildesk",
    "author": "Metzler IT GmbH",
    "support": "support@mit-odoo.com",
    "website": "https://mit-odoo.com/module/maildesk",
    "license": "OPL-1",
    "category": "Productivity",
    "depends": ["web", "contacts", "mail", "microsoft_outlook", "google_gmail"],
    "external_dependencies": {
        "python": [
            "imapclient",
            "google-api-python-client",
            "google-auth",
            "google-auth-httplib2",
            "msal",
        ],
    },
    "demo": [
        "data/demo/01_fetchmail_servers_demo.xml",
        "data/demo/02_mailbox_accounts_demo.xml",
        "data/demo/03_mailbox_folders_demo.xml",
        "data/demo/04_mail_tags_demo.xml",
        "data/demo/05_message_index_demo.xml",
        "data/demo/06_mail_message_threading_demo.xml",
        "data/demo/07_ui_cache_demo.xml",
        "data/demo/08_attachments_demo.xml",
        "data/demo/09_drafts_demo.xml",
        "data/demo/10_res_groups_demo.xml",
        "data/demo/11_message_index_demo_pro.xml",
        "data/demo/12_ui_cache_demo_pro.xml",
        "data/demo/13_message_index_bulk_demo.xml",
        "data/demo/14_ui_cache_bulk_demo.xml",
    ],
    "images": [
        "static/description/banner.gif",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
        "data/ir_cron.xml",
        "wizard/mailbox_account_wizard.xml",
        "wizard/mail_compose_message_wizard.xml",
        "views/mailbox_account_views.xml",
        "views/maildesk_message_index_views.xml",
        "views/maildesk_ui_cache_views.xml",
        "views/maildesk_ingest_queue_views.xml",
        "views/mail_message_tag.xml",
        "views/res_partner_views.xml",
        "views/mail_message_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus_views.xml",
        "views/mail_mail_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "web/static/lib/jquery/jquery.js",
            "maildesk_mail_client/static/src/scss/maildesk.scss",
            # Services (load before components)
            "maildesk_mail_client/static/src/js/services/maildesk_store.esm.js",
            "maildesk_mail_client/static/src/js/services/maildesk_sync.esm.js",
            "maildesk_mail_client/static/src/js/services/maildesk_notification.esm.js",
            # Hooks (OWL-based reusable logic)
            "maildesk_mail_client/static/src/hooks/useIframeResize.esm.js",
            "maildesk_mail_client/static/src/hooks/useMessageSelection.esm.js",
            # Utils (pure functions, no OWL)
            "maildesk_mail_client/static/src/utils/maildesk_iframe.esm.js",
            "maildesk_mail_client/static/src/utils/maildesk_dom.esm.js",
            # Components - Fields
            "maildesk_mail_client/static/src/components/fields/email_input/email_input_field.esm.js",
            "maildesk_mail_client/static/src/components/fields/email_input/email_input_field.xml",
            # Components - Main
            "maildesk_mail_client/static/src/js/maildesk.esm.js",
            "maildesk_mail_client/static/src/xml/maildesk.xml",
            # Core - Global Composer (Pattern mirrored from Odoo Mail)
            "maildesk_mail_client/static/src/core/composer/composer.scss",
            "maildesk_mail_client/static/src/core/composer/composer_record.esm.js",
            "maildesk_mail_client/static/src/core/composer/composer_service.esm.js",
            "maildesk_mail_client/static/src/core/composer/composer_input.esm.js",
            "maildesk_mail_client/static/src/core/composer/composer_input.xml",
            "maildesk_mail_client/static/src/core/composer/composer_window.esm.js",
            "maildesk_mail_client/static/src/core/composer/composer_window.xml",
            "maildesk_mail_client/static/src/core/composer/composer_container.esm.js",
            "maildesk_mail_client/static/src/core/composer/composer_container.xml",
            "maildesk_mail_client/static/src/core/composer/composer_bubble.esm.js",
            "maildesk_mail_client/static/src/core/composer/composer_bubble.xml",
            "maildesk_mail_client/static/src/core/composer/main_components.esm.js",
            # Components - Systray
            "maildesk_mail_client/static/src/components/composer/compose_systray.esm.js",
            "maildesk_mail_client/static/src/components/composer/compose_systray.xml",
            # Components - Dialogs
            "maildesk_mail_client/static/src/components/dialogs/assign_tags/assign_tags_dialog.esm.js",
            "maildesk_mail_client/static/src/components/dialogs/assign_tags/assign_tags_dialog.xml",
            "maildesk_mail_client/static/src/components/dialogs/contact_picker/contact_picker_dialog.esm.js",
            "maildesk_mail_client/static/src/components/dialogs/contact_picker/contact_picker_dialog.xml",
            "maildesk_mail_client/static/src/components/dialogs/move_to_folder/move_to_folder_dialog.esm.js",
            "maildesk_mail_client/static/src/components/dialogs/move_to_folder/move_to_folder_dialog.xml",
            # Components - Popovers
            "maildesk_mail_client/static/src/components/popovers/partner_card/partner_card_popover.esm.js",
            "maildesk_mail_client/static/src/components/popovers/partner_card/partner_card_popover.xml",
            # Components - MailDesk Child Components
            "maildesk_mail_client/static/src/components/maildesk/undo_toast/undo_toast.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/undo_toast/undo_toast.xml",
            "maildesk_mail_client/static/src/components/maildesk/filter_menu/filter_menu.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/filter_menu/filter_menu.xml",
            "maildesk_mail_client/static/src/components/maildesk/folder_tree/folder_tree.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/folder_tree/folder_tree.xml",
            "maildesk_mail_client/static/src/components/maildesk/mail_list/mail_list.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/mail_list/mail_list.xml",
            "maildesk_mail_client/static/src/components/maildesk/mail_detail/mail_detail.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/mail_detail/mail_detail.xml",
            "maildesk_mail_client/static/src/components/maildesk/thread_message/thread_message.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/thread_message/thread_message.xml",
            "maildesk_mail_client/static/src/components/maildesk/thread_container/thread_container.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/thread_container/thread_container.xml",
            "maildesk_mail_client/static/src/components/maildesk/toolbar/toolbar.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/toolbar/toolbar.xml",
            "maildesk_mail_client/static/src/components/maildesk/debug_stats/debug_stats.esm.js",
            "maildesk_mail_client/static/src/components/maildesk/debug_stats/debug_stats.xml",
        ],
        "web.assets_unit_tests": [
            "maildesk_mail_client/static/tests/common.js",
            "maildesk_mail_client/static/tests/maildesk_notification.test.js",
            "maildesk_mail_client/static/tests/maildesk_store.test.js",
            "maildesk_mail_client/static/tests/maildesk_sync.test.js",
        ],
    },
    "application": True,
    "price": 249.00,
    "currency": "EUR",
    "sequence": 1,
}
