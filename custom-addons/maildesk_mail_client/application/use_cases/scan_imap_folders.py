# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Scan IMAP Folders.

Implements the application-level use case for Scan IMAP Folders.
Layer: application.
"""

import logging

from ...application.services.imap_client_service import build_authenticated_imap_client
from ...infrastructure.utils.imap_encoding import safe_folder_operation

_logger = logging.getLogger(__name__)


class ScanImapFolders:
    """
    Phase 1 of Two-Phase Sync: Cheap Scan.

    Check STATUS (UIDNEXT, HIGHESTMODSEQ) for all incremental folders
    in the account to detect changes WITHOUT fetching messages.
    """

    def __init__(self, env):
        self.env = env

    def execute(self, account):
        """
        Scan all incremental folders for changes.
        """
        # Fix: Check server_type via mail_server_id relationship
        if not account.mail_server_id or account.mail_server_id.server_type != "imap":
            return

        # 1. Select folders that are relevant for sync (skip trash/spam if configured, or just sync all)
        # We only scan folders that have completed backfill (incremental state).
        folders = self.env["mailbox.folder"].search(
            [
                ("account_id", "=", account.id),
                ("sync_state", "=", "incremental"),
            ]
        )

        if not folders:
            return

        _logger.info(
            "Phase 1: Scanning %d folders for account %s", len(folders), account.name
        )

        try:
            with build_authenticated_imap_client(self.env, account) as client:
                for folder in folders:
                    if not folder.imap_name:
                        continue

                    try:
                        # STATUS command is lightweight
                        # We request UIDNEXT, UIDVALIDITY, HIGHESTMODSEQ, and UNSEEN
                        status_fields = ["UIDNEXT", "UIDVALIDITY", "UNSEEN"]
                        if client.has_capability("CONDSTORE"):
                            status_fields.append("HIGHESTMODSEQ")

                        # Use safe_folder_operation for robust error handling
                        def get_status():
                            return client.status(folder.imap_name, status_fields)

                        resp = safe_folder_operation(
                            "STATUS", folder.imap_name, get_status
                        )
                        if not resp:
                            # STATUS not supported for this folder - skip it
                            _logger.debug(
                                f"STATUS not available for folder {folder.imap_name} "
                                "(server may not support it for this folder type)"
                            )
                            continue

                        # Try to find folder data with various encodings and cases
                        folder_data = None

                        # Try exact match first (string)
                        folder_data = resp.get(folder.imap_name)

                        # Try bytes encoding
                        if not folder_data:
                            try:
                                folder_data = resp.get(folder.imap_name.encode("utf-8"))
                            except UnicodeEncodeError:
                                folder_data = None

                        # Try case-insensitive match (some servers change case)
                        if not folder_data:
                            folder_name_lower = folder.imap_name.lower()
                            for key, value in resp.items():
                                key_str = (
                                    key.decode("utf-8")
                                    if isinstance(key, bytes)
                                    else str(key)
                                )
                                if key_str.lower() == folder_name_lower:
                                    folder_data = value
                                    break

                        if not folder_data:
                            _logger.debug(
                                "No STATUS data for folder %s", folder.imap_name
                            )
                            continue

                        # Extract values
                        uidnext = int(
                            folder_data.get(b"UIDNEXT")
                            or folder_data.get("UIDNEXT")
                            or 0
                        )
                        uidvalidity = int(
                            folder_data.get(b"UIDVALIDITY")
                            or folder_data.get("UIDVALIDITY")
                            or 0
                        )

                        modseq_raw = folder_data.get(
                            b"HIGHESTMODSEQ"
                        ) or folder_data.get("HIGHESTMODSEQ")
                        highest_modseq = str(int(modseq_raw)) if modseq_raw else "0"

                        # Update UNREAD COUNT (if changed)
                        unseen = int(
                            folder_data.get(b"UNSEEN") or folder_data.get("UNSEEN") or 0
                        )
                        if folder.unread_count != unseen:
                            folder.sudo().write(
                                {
                                    "unread_count": unseen,
                                    "unread_count_updated_at": self.env.cr.now(),  # Update cache timestamp
                                }
                            )

                        # Detecting Changes
                        is_dirty = False

                        # 1. UIDNEXT Changed? (New messages arrived)
                        if uidnext > folder.last_uidnext:
                            is_dirty = True

                        # 2. MODSEQ Changed? (Flags changed or messages deleted/expunged)
                        if (
                            highest_modseq != "0"
                            and highest_modseq != folder.last_highest_modseq
                        ):
                            is_dirty = True

                        # 3. UIDVALIDITY Changed? (Folder reset - requires full resync)
                        if folder.uid_validity and uidvalidity != folder.uid_validity:
                            _logger.warning(
                                "UIDVALIDITY changed for %s! Triggering heavy resync logic.",
                                folder.imap_name,
                            )
                            is_dirty = True

                        if is_dirty:
                            _logger.info(
                                "Folder %s marked DIRTY (UIDNEXT: %s->%s, MODSEQ: %s->%s)",
                                folder.imap_name,
                                folder.last_uidnext,
                                uidnext,
                                folder.last_highest_modseq,
                                highest_modseq,
                            )
                            folder.write(
                                {
                                    "needs_sync": True,
                                    # We DO NOT update last_uidnext here!
                                    # We only update it AFTER successful sync in Phase 2.
                                }
                            )
                        else:
                            # Not dirty. Should we clear needs_sync?
                            # No, maybe it was set dirty manually or by previous failed sync.
                            # But if the current status matches the LAST SUCCESSFUL sync status,
                            # it implies no changes since last sync.
                            # If `needs_sync` is True but scan says "no change from last_uidnext",
                            # it means `last_uidnext` is ALREADY current.
                            # So `needs_sync` might be stale or set for other reasons (e.g. manual trigger).
                            # We leave `needs_sync` as is to be safe, or we could optimize.
                            # User rule: "Scan phase... Mark folder as dirty". It implies we ADD dirty, not remove.
                            pass

                    except Exception as e:
                        if getattr(e, "pgcode", None) == "40001":
                            raise
                        _logger.error(
                            "Failed to scan folder %s: %s", folder.imap_name, e
                        )
                        # Continue to next folder

        except Exception as e:
            _logger.error("Phase 1 Scan failed for account %s: %s", account.name, e)
