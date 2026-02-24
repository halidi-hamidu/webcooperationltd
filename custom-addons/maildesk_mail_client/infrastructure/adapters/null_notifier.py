# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Null implementation of SSotChangeNotifier for testing.

Provides a no-op notifier that can be used in unit tests
to avoid infrastructure dependencies.
"""


class NullNotifier:
    """
    Null Object implementation of SSotChangeNotifier Protocol.

    Does nothing when called - useful for unit tests that want to
    avoid bus infrastructure or suppress notifications.
    """

    def notify_flags_changed(self, account_id, folder, uids, **kwargs):
        """No-op: silently ignore flag change notifications."""
        pass

    def notify_messages_added(self, account_id, folder, uids, **kwargs):
        """No-op: silently ignore new message notifications."""
        pass

    def notify_messages_moved(
        self, account_id, source_folder, destination_folder, uids
    ):
        """No-op: silently ignore move notifications."""
        pass

    def notify_messages_deleted(self, account_id, folder, uids):
        """No-op: silently ignore deletion notifications."""
        pass

    def notify_full_refresh(self, account_id, folder=None):
        """No-op: silently ignore refresh notifications."""
        pass
