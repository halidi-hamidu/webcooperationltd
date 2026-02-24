# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk test helpers.

Provides small fakes/stubs used by multiple unit/integration tests to keep tests
deterministic and independent of external providers.
Layer: tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class NotifierCall:
    """Captured notifier call for assertions."""

    name: str
    args: Tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = field(default_factory=dict)


class FakeNotifier:
    """Captures SSOT/bus notifications emitted by use cases."""

    def __init__(self):
        self.calls: List[NotifierCall] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append(NotifierCall(name=name, args=args, kwargs=kwargs))

    def notify_flags_changed(self, *args: Any, **kwargs: Any) -> None:
        self._record("notify_flags_changed", *args, **kwargs)

    def notify_messages_added(self, *args: Any, **kwargs: Any) -> None:
        self._record("notify_messages_added", *args, **kwargs)

    def notify_messages_deleted(self, *args: Any, **kwargs: Any) -> None:
        self._record("notify_messages_deleted", *args, **kwargs)

    def notify_unread_count_changed(self, *args: Any, **kwargs: Any) -> None:
        self._record("notify_unread_count_changed", *args, **kwargs)

    def notify_messages_moved(self, *args: Any, **kwargs: Any) -> None:
        self._record("notify_messages_moved", *args, **kwargs)

    def notify_refresh(self, *args: Any, **kwargs: Any) -> None:
        self._record("notify_refresh", *args, **kwargs)

    def notify_full_refresh(self, *args: Any, **kwargs: Any) -> None:
        self._record("notify_full_refresh", *args, **kwargs)


@contextmanager
def context_manager_return(value: Any):
    """Minimal context manager yielding a provided value."""

    yield value


class DummyImapEnvelope:
    """Minimal IMAP ENVELOPE-like object used by bootstrap/backfill tests."""

    def __init__(
        self,
        *,
        subject: Optional[bytes] = None,
        from_: Optional[list] = None,
        to: Optional[list] = None,
        cc: Optional[list] = None,
        bcc: Optional[list] = None,
        date: Optional[bytes] = None,
    ):
        self.subject = subject
        self.from_ = from_ or []
        self.to = to or []
        self.cc = cc or []
        self.bcc = bcc or []
        self.date = date


class DummyImapAddress:
    """Minimal IMAP Address-like object."""

    def __init__(
        self,
        *,
        name: Optional[bytes] = None,
        mailbox: Optional[bytes] = None,
        host: Optional[bytes] = None,
    ):
        self.name = name
        self.mailbox = mailbox
        self.host = host
