# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
MessageIndexQueryRepo: Read-side CQRS query repository

Isolates all ORM queries for message_index list views.
Optimized for single-query list fetches with tag filtering and priority sorting.
"""

import logging

_logger = logging.getLogger(__name__)


class MessageIndexQueryRepo:
    """
    Repository for querying message_index denormalized read model (UI list views).

    Responsibilities:
    - Single-query search with tag_ids preloaded
    - SQL-level tag filtering (no Python loops)
    - Priority sorting (starred → unread → date)
    - Pagination with deterministic ordering

    Clean Architecture:
    - SSOTListAdapter calls this repository
    - ListMessagesSsot use case doesn't know about this
    """

    def __init__(self, env):
        """
        Args:
            env: Odoo environment (injected by adapter)
        """
        self._env = env

    def search_for_list(
        self,
        account_id,
        folder,
        provider,
        account_email=None,
        direction=None,
        offset=0,
        limit=30,
        tag_ids=None,
        search_term=None,
        email_filter=None,
        unread_first=False,
        starred_first=False,
    ):
        """
        Bounded 2-query search for UI list view (PostgreSQL-safe).
        ...
        Args:
            email_filter: Optional email address to filter by (Participation: From/To/Cc/Bcc)
        ...
        """
        Index = self._env["maildesk.message_index"].sudo()

        # Build domain
        #
        # IMPORTANT: Do not filter by `provider` here.
        #
        # The mailbox account ID is the authoritative scope for list queries.
        # `provider` is derived from account configuration (smart detection) and
        # may drift across migrations (e.g. legacy SSOT rows stored as "imap").
        # Filtering by provider would incorrectly hide otherwise valid rows.
        domain = [
            ("account_id", "=", account_id),
            # Be tolerant to legacy NULLs (treat NULL as False).
            ("deleted_on_server", "!=", True),
            ("pending_delete", "!=", True),
        ]

        # Direction filter: refine by inferred direction, independent of folder selection.
        # Semantics:
        # - outgoing: message sent by this mailbox (From contains account email)
        # - incoming: message NOT sent by this mailbox (From does not contain account email)
        #
        # This keeps folder selection AND direction filter intersected, which matches the UI:
        # if a folder is selected, we search within it; direction further narrows results.
        direction = (direction or "").strip().lower()
        if direction in {"incoming", "outgoing"} and account_email:
            ae = str(account_email).strip()
            if ae:
                if direction == "outgoing":
                    domain.append(("from_addr", "ilike", ae))
                else:
                    # Include rows with missing from_addr as incoming (fail-open).
                    domain.extend(
                        ["|", ("from_addr", "=", False), ("from_addr", "not ilike", ae)]
                    )

        if folder is not None and direction in {"incoming", "outgoing"}:
            # Direction filters operate on the "physical folder" scope and must NOT
            # use pending-move logic.
            #
            # NOTE: We prefer exact matching here (fast, predictable). Folder names
            # used for direction filters are sourced from mailbox.folder mapping
            # (imap_name/display_name), so they should already be canonical for the DB.
            if isinstance(folder, (list, tuple, set)):
                folders = [str(f).strip() for f in folder if f and str(f).strip()]
                folders = list(dict.fromkeys(folders))
                if folders:
                    domain.append(("folder", "in", folders))
            else:
                domain.append(("folder", "=", str(folder).strip()))
        elif folder is not None:
            if isinstance(folder, (list, tuple, set)):
                folders = [str(f).strip() for f in folder if f and str(f).strip()]
                if folders:
                    domain_move = [
                        "|",
                        "&",
                        ("folder", "in", folders),
                        ("pending_move_to", "=", False),
                        ("pending_move_to", "in", folders),
                    ]
                    domain.extend(domain_move)
            else:
                domain_move = [
                    "|",
                    "&",
                    ("folder", "=", folder),
                    ("pending_move_to", "=", False),
                    ("pending_move_to", "=", folder),
                ]
                domain.extend(domain_move)

        if tag_ids:
            domain.append(("tag_ids", "in", tag_ids))

        if unread_first:
            domain.append(("is_read", "=", False))

        if starred_first:
            domain.append(("is_starred", "=", True))

        # PARTNER FILTER (Participation Logic)
        # Must appear in From OR To OR Cc OR Bcc
        if email_filter:
            ef = email_filter.strip()
            if ef:
                # Odoo Domain: ['|', '|', '|', A, B, C, D] means (A OR B OR C OR D)
                domain.extend(
                    [
                        "|",
                        "|",
                        "|",
                        ("from_addr", "ilike", ef),
                        ("to_addrs", "ilike", ef),
                        ("cc_addrs", "ilike", ef),
                        ("bcc_addrs", "ilike", ef),
                    ]
                )

        # Full-text search on subject/from/to/cc
        if search_term:
            _logger.info(f"[Search] Adding search_term='{search_term}' to domain")

            # --- QUICK WIN: Search in Local Body Cache (opened emails) ---
            # Search json_cache->body->body_text for the term
            # This allows finding messages by body IF they have been opened/cached locally.
            sql = """
                SELECT index_id
                FROM maildesk_ui_cache
                WHERE json_cache->'body'->>'body_text' ILIKE %s
            """
            self._env.cr.execute(sql, (f"%{search_term}%",))
            cached_match_ids = [r[0] for r in self._env.cr.fetchall()]

            if cached_match_ids:
                _logger.info(
                    f"[Search] Found {len(cached_match_ids)} matches in local body cache"
                )

            domain.append("|")
            domain.append("|")
            domain.append("|")
            domain.append("|")  # Extra OR for cache matches
            domain.append(("subject", "ilike", search_term))
            domain.append(("from_addr", "ilike", search_term))
            domain.append(("to_addrs", "ilike", search_term))
            domain.append(("cc_addrs", "ilike", search_term))

            if cached_match_ids:
                domain.append(("id", "in", cached_match_ids))
            else:
                # If no cache matches, we still need a valid domain tuple for the OR
                # using a clearly false condition or just reusing subject to keep domain valid
                domain.append(("id", "=", -1))

        total = Index.search_count(domain)
        if self._env.context.get("maildesk_debug_list_domain"):
            _logger.info(
                "[MailDesk][List][Debug] account_id=%s provider_arg=%s folder_arg=%s domain=%s total=%s",
                account_id,
                provider,
                folder,
                domain,
                total,
            )

        # Build ORDER BY clause for priority sorting
        order_clauses = []
        # Even with filtering, we keep sorting logic for consistency
        # sort_ts is the primary sort key for time-based ordering
        order_clauses.append("sort_ts DESC")  # Most recent first
        order_clauses.append("id DESC")  # Deterministic tie-breaker

        order = ", ".join(order_clauses)

        # === BOUNDED 2-QUERY PATTERN ===

        # Query 1: Fetch top-N IDs using index (fast, bounded, deterministic)
        # This uses the composite index and returns only IDs (minimal data transfer)
        id_records = Index.search(domain, offset=offset, limit=limit, order=order)

        if not id_records:
            return Index.browse([]), total

        # Query 2: Preload ALL data for bounded set of IDs
        # This includes tag_ids via Odoo's read() which batches tag preloading
        # No N+1: single query for main data + single query for all tags
        ids_to_fetch = id_records.ids

        # Re-fetch with full data including tag preloading
        # Odoo's browse() + read() ensures tags are preloaded efficiently
        records = Index.browse(ids_to_fetch)

        # Force tag preloading by accessing tag_ids (Odoo batches this)
        # This triggers a single SQL query to fetch all tags for all records
        if records:
            _ = records.mapped("tag_ids")  # Force prefetch

        # Preserve original sort order (IDs were fetched in order)
        # Create a mapping to preserve order
        id_to_record = {rec.id: rec for rec in records}
        sorted_records = Index.browse([])
        for record_id in ids_to_fetch:
            if record_id in id_to_record:
                sorted_records += id_to_record[record_id]

        return sorted_records, total

    def search_all_accounts(
        self,
        account_ids,
        offset=0,
        limit=30,
        tag_ids=None,
        search_term=None,
        email_filter=None,
        unread_first=False,
        starred_first=False,
    ):
        """
        Cross-account search for unified inbox view (bounded 2-query pattern).

        Similar to search_for_list but searches across multiple accounts.
        Used when user selects "All Accounts" in UI.

        Args:
            account_ids: List of account IDs to search
            Other args: Same as search_for_list

        Returns:
            (records, total_count)
        """
        Index = self._env["maildesk.message_index"].sudo()

        domain = [
            ("account_id", "in", account_ids),
            # Be tolerant to legacy NULLs (treat NULL as False).
            ("deleted_on_server", "!=", True),
            # OPTIMISTIC UI alignment
            ("pending_delete", "!=", True),
        ]

        if tag_ids:
            domain.append(("tag_ids", "in", tag_ids))

        if email_filter:
            ef = email_filter.strip()
            if ef:
                domain.extend(
                    [
                        "|",
                        "|",
                        "|",
                        ("from_addr", "ilike", ef),
                        ("to_addrs", "ilike", ef),
                        ("cc_addrs", "ilike", ef),
                        ("bcc_addrs", "ilike", ef),
                    ]
                )

        if search_term:
            # --- QUICK WIN: Search in Local Body Cache (opened emails) ---
            sql = """
                SELECT index_id
                FROM maildesk_ui_cache
                WHERE json_cache->'body'->>'body_text' ILIKE %s
            """
            self._env.cr.execute(sql, (f"%{search_term}%",))
            cached_match_ids = [r[0] for r in self._env.cr.fetchall()]

            domain.append("|")
            domain.append("|")
            domain.append("|")
            domain.append("|")
            domain.append(("subject", "ilike", search_term))
            domain.append(("from_addr", "ilike", search_term))
            domain.append(("to_addrs", "ilike", search_term))
            domain.append(("cc_addrs", "ilike", search_term))

            if cached_match_ids:
                domain.append(("id", "in", cached_match_ids))
            else:
                domain.append(("id", "=", -1))

        total = Index.search_count(domain)

        order_clauses = []
        if starred_first:
            order_clauses.append("is_starred DESC")
        if unread_first:
            order_clauses.append("is_read ASC")
        order_clauses.append("sort_ts DESC")
        order_clauses.append("id DESC")

        order = ", ".join(order_clauses)

        # Bounded 2-query pattern (same as search_for_list)
        id_records = Index.search(domain, offset=offset, limit=limit, order=order)

        if not id_records:
            return Index.browse([]), total

        ids_to_fetch = id_records.ids
        records = Index.browse(ids_to_fetch)

        # Force tag preloading
        if records:
            _ = records.mapped("tag_ids")

        # Preserve sort order
        id_to_record = {rec.id: rec for rec in records}
        sorted_records = Index.browse([])
        for record_id in ids_to_fetch:
            if record_id in id_to_record:
                sorted_records += id_to_record[record_id]

        return sorted_records, total
