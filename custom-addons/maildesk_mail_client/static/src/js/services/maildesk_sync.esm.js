// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk MailDesk Sync.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { registry } from "@web/core/registry";

/**
 * MailDesk Sync Service
 *
 * ARCHITECTURE INVARIANTS:
 * - Polling exists ONLY to accelerate detection of backend changes
 * - Polling MUST NOT be responsible for UI freshness
 * - UI freshness is guaranteed by: backend state, bus events, refresh on focus
 * - Polling is GLOBAL — NOT per account, NOT per folder, NOT per user
 * - Backend decides which accounts are eligible for sync
 * - Frontend only triggers "check if anything changed"
 *
 * CONFIGURATION:
 * - All polling settings come from /maildesk/config (ir.config_parameter)
 * - NO hardcoded intervals in this file
 *
 * MULTI-TAB:
 * - If only_main_tab=true, only one tab polls
 * - Uses multi_tab service for coordination
 *
 * Pattern: Singleton service with explicit start/stop lifecycle
 */

class MailDeskSyncService {
    constructor(env, dependencies) {
        this.env = env;
        this.orm = dependencies.orm;
        this.busService = dependencies.bus_service;
        this.store = dependencies["maildesk.store"];
        this.notificationService = dependencies["maildesk.notification"];
        this.multiTab = dependencies.multi_tab;

        // Configuration (defaults)
        this._config = {
            enabled: true,
            interval_seconds: 15,
            only_main_tab: true,
            pause_on_hidden: false,
        };

        // Polling state
        this._pollInterval = null;
        this._pollInFlight = false;
        this._isPaused = false;

        // Bus subscription state
        this._busListenersStarted = false;
        /** @type {Map<string, Function>} */
        this._busTypeToListener = new Map();
        /** @type {Set<string>} */
        this._accountChannels = new Set();
        this._userChannelAdded = false;
        this._notifyEnabledSinceMs = 0;
        this._presenceInterval = null;

        // Visibility change handler
        this._visibilityHandler = this._onVisibilityChange.bind(this);
    }


    // CONFIGURATION


    get config() {
        return this._config;
    }


    // BUS SUBSCRIPTION LIFECYCLE


    startBusListeners() {
        if (this._busListenersStarted) {
            console.warn("[MailDesk Sync] Bus listeners already active");
            return;
        }

        // Ensure bus connection exists (addChannel also starts it, but this helps prove wiring).
        this.busService.start();
        this._startPresenceHeartbeat();

        this.busService.addEventListener("BUS:CONNECT", () => {
            this._notifyEnabledSinceMs = Date.now();
            console.log("[MailDesk Sync] Bus connected", {
                workerState: this.busService.workerState,
                lastNotificationId: this.busService.lastNotificationId,
            });
            this._startPresenceHeartbeat();
        });
        this.busService.addEventListener("BUS:DISCONNECT", (ev) => {
            console.warn("[MailDesk Sync] Bus disconnected", ev?.detail);
            this._stopPresenceHeartbeat();
        });
        this.busService.addEventListener("BUS:RECONNECT", () => {
            this._notifyEnabledSinceMs = Date.now();
            console.log("[MailDesk Sync] Bus reconnected");
            this._startPresenceHeartbeat();
        });

        const register = (type, listener) => {
            this._busTypeToListener.set(type, listener);
            this.busService.subscribe(type, listener);
        };

        register("maildesk.account/flags_changed", (payload) => {
            this._applyFlagsChanged(payload);
        });
        register("maildesk.account/messages_added", (payload) => {
            this._applyMessagesAdded(payload);
        });
        register("maildesk.account/messages_moved", (payload) => {
            this._applyMessagesMoved(payload);
        });
        register("maildesk.account/messages_deleted", (payload) => {
            this._applyMessagesDeleted(payload);
        });
        register("maildesk.account/tags_changed", (payload) => {
            this._applyTagsChanged(payload);
        });
        register("maildesk.account/refresh", (payload) => {
            this._applyRefresh(payload);
        });
        register("maildesk.notify/new_messages", (payload) => {
            this._applyUserNewMessagesNotification(payload);
        });
        register("maildesk.account/unread_count_changed", (payload) => {
            this._applyUnreadCountChanged(payload);
        });

        this._busListenersStarted = true;
    }


    _applyUnreadCountChanged(payload) {
        const { account_id, folder, count } = payload;

        // Context Separation Guard:
        // If we are in "Context Mode" (Partner Filter or Search active),
        // we MUST ignore realtime unread updates.
        // The backend only sends global/absolute counts, which would overwrite
        // our correctly filtered context counts.
        if (this.store.partnerId || this.store.searchQuery) {
            console.debug(
                `[MailDesk Sync] Ignored realtime unread update (Context Mode active): ` +
                `account=${account_id}, folder=${folder}, global_count=${count}`
            );
            return;
        }

        // Find folder in store
        const folderId = this.store.findFolderId(account_id, folder);

        if (folderId) {
            // Absolute update from SSOT
            if (count !== undefined) {
                this.store.setFolderUnreadCount(folderId, count);
                console.debug(`[MailDesk Sync] Updated unread count for folder ${folder}: -> ${count}`);
            }
        } else {
            console.warn(`[MailDesk Sync] Unread count update for unknown folder: ${folder} (account ${account_id})`);
        }
    }

    stopBusListeners() {
        if (this._busListenersStarted) {
            for (const [type, listener] of this._busTypeToListener.entries()) {
                this.busService.unsubscribe(type, listener);
            }
            this._busTypeToListener.clear();
            this._busListenersStarted = false;
        }

        // Remove only channels registered by this service instance.
        for (const channel of this._accountChannels) {
            this.busService.deleteChannel(channel);
        }
        this._accountChannels.clear();
        if (this._userChannelAdded) {
            this.busService.deleteChannel("maildesk.user");
            this._userChannelAdded = false;
        }
        this._stopPresenceHeartbeat();
        console.log("[MailDesk Sync] Bus listeners stopped");
    }

    async _ensureUserChannel() {
        this.startBusListeners();
        if (this._userChannelAdded) {
            return;
        }
        console.log("[MailDesk Sync] Adding bus channel: maildesk.user");
        await this.busService.addChannel("maildesk.user");
        this._userChannelAdded = true;
        console.log("[MailDesk Sync] Bus channel active: maildesk.user");
        this._startPresenceHeartbeat();
    }

    /**
     * Subscribe the websocket to mailbox account channels.
     *
     * Server-side access control is enforced in `ir.websocket` by mapping the
     * requested string channel to the corresponding `mailbox.account` record
     * only when the current user is in `access_user_ids`.
     *
     * @param {number[]} accountIds
     */
    async ensureAccountChannels(accountIds) {
        const ids = (accountIds || []).map((id) => Number(id)).filter(Boolean);
        if (!ids.length) {
            return;
        }
        await this._ensureUserChannel();
        await Promise.all(
            ids.map(async (accountId) => {
                const channel = `mailbox.account_${accountId}`;
                if (this._accountChannels.has(channel)) {
                    return;
                }
                console.log("[MailDesk Sync] Adding bus channel:", channel);
                await this.busService.addChannel(channel);
                this._accountChannels.add(channel);
                console.log("[MailDesk Sync] Bus channel active:", channel);
            })
        );
    }

    /**
     * Apply flag changes to store.
     * Updates message flags in-place (OWL reacts to object property changes).
     *
     * Lookup strategy: Iterate store.messages Object and match by uid + folder imap_name
     */
    _applyFlagsChanged(payload) {
        const { account_id, folder, uids, index_ids, flags } = payload;

        if ((!uids || uids.length === 0) && (!index_ids || index_ids.length === 0)) {
            return;
        }

        if (!this.store?.messages) {
            console.warn("[Bus→Store] No store.messages available");
            return;
        }

        const uidSet = new Set((uids || []).map((u) => String(u)));
        const indexIdSet = new Set((index_ids || []).map((i) => String(i)));

        let updatedCount = 0;

        // Iterate object values.
        for (const msgKey in this.store.messages) {
            const message = this.store.messages[msgKey];

            const msgAccountId = Array.isArray(message.account_id)
                ? message.account_id[0]
                : message.account_id;
            if (msgAccountId !== account_id) {
                continue;
            }

            const msgIndexId = String(message.id);
            const msgUid = String(message.uid ?? "");
            const matches = indexIdSet.size
                ? indexIdSet.has(msgIndexId)
                : uidSet.has(msgUid || msgIndexId);
            if (!matches) {
                continue;
            }

            const folderRec = this.store.folders?.[message.folder_id];
            const msgFolderName = folderRec?.imap_name || folderRec?.name;
            if (folder && msgFolderName && msgFolderName !== folder) {
                continue;
            }

            if (folder && !msgFolderName) {
                // Be conservative if folder metadata isn't loaded yet.
                continue;
            }

            // Match found: mutate in place (OWL reactive)
            {
                // In-place mutation (OWL reactive).
                if (flags.is_read !== undefined && flags.is_read !== null) {
                    message.is_read = flags.is_read;
                }
                if (flags.is_starred !== undefined && flags.is_starred !== null) {
                    message.is_starred = flags.is_starred;
                }

                updatedCount++;
            }
        }

        if (updatedCount === 0) {
            // This is NORMAL - message might be in different folder or not loaded yet
            console.debug(
                `[Bus→Store] Messages not in current store (expected): ` +
                `account=${account_id}, folder=${folder}, uids=${(uids || []).slice(0, 3)}` +
                ((uids || []).length > 3 ? ` (+${(uids || []).length - 3} more)` : "")
            );
            // If we're currently viewing the affected folder, force a refresh to sync SSOT state
            // (covers edge cases where message identity fields differ).
            this._refreshIfCurrentFolder({ account_id, folder });
        }
    }

    /**
     * Apply new messages event.
     *
     * Architecture:
     * - Notifications triggered DIRECTLY from bus payload (domain event)
     * - UI refresh is a SEPARATE concern
     * - No dependency on currentFolder or store state
     */
    _applyMessagesAdded(payload) {
        const { account_id, folder, uids, count } = payload;

        // Refresh UI if viewing affected folder.
        this._refreshIfCurrentFolder({ account_id, folder });
    }

    _applyUserNewMessagesNotification(payload) {
        const parseEmittedAtMs = (emittedAt) => {
            if (!emittedAt) {
                return NaN;
            }
            // Backend should send UTC (`...Z`). If it doesn't, browsers parse as local time,
            // which can make a fresh event look "stale" and get dropped.
            const normalized =
                typeof emittedAt === "string" && /Z$|[+-]\\d\\d:\\d\\d$/.test(emittedAt)
                    ? emittedAt
                    : `${String(emittedAt)}Z`;
            return Date.parse(normalized);
        };
        const emittedAtMs =
            typeof payload?.emitted_at_ms === "number"
                ? payload.emitted_at_ms
                : payload?.emitted_at
                    ? parseEmittedAtMs(payload.emitted_at)
                    : NaN;
        // Allow small clock skews / event ordering jitter.
        const skewToleranceMs = 10_000;
        if (
            !Number.isNaN(emittedAtMs) &&
            this._notifyEnabledSinceMs &&
            emittedAtMs < (this._notifyEnabledSinceMs - skewToleranceMs)
        ) {
            return;
        }

        const messages = payload?.messages || [];
        if (Array.isArray(messages) && messages.length) {
            this._triggerNotifications(messages);
        }
    }

    async _pingPresence() {
        try {
            await this.orm.call("maildesk.ui_presence", "ping", []);
        } catch (e) {
            // Presence is best-effort; do not break bus.
        }
    }

    _startPresenceHeartbeat() {
        if (this._presenceInterval) {
            return;
        }
        // Set interval FIRST to prevent race condition with concurrent calls
        this._presenceInterval = setInterval(() => {
            void this._pingPresence();
        }, 30000);
        // Then do initial ping
        void this._pingPresence();
    }

    _stopPresenceHeartbeat() {
        if (this._presenceInterval) {
            clearInterval(this._presenceInterval);
            this._presenceInterval = null;
        }
    }


    /**
     * Apply full refresh event.
     * Signals UI to reload message list.
     */
    _applyRefresh(payload) {
        const { account_id, folder } = payload;

        this._refreshIfCurrentFolder({ account_id, folder });
    }

    _applyMessagesMoved(payload) {
        const { account_id, source_folder, destination_folder, count } = payload;
        this._refreshIfCurrentFolder({
            account_id,
            folder: source_folder,
            alsoMatch: destination_folder,
        });
    }

    _applyMessagesDeleted(payload) {
        const { account_id, folder, count } = payload;
        this._refreshIfCurrentFolder({ account_id, folder });
    }

    /**
     * Apply tag changes to store.
     * Updates message tags in-place (OWL reacts to object property changes).
     *
     * Similar pattern to _applyFlagsChanged but for tag_ids.
     */
    _applyTagsChanged(payload) {
        const { account_id, folder, uids, tags } = payload;

        if (!uids || uids.length === 0) {
            return;
        }

        if (!this.store?.messages) {
            console.warn("[Bus→Store] No store.messages available");
            return;
        }

        const uidSet = new Set(uids.map((u) => String(u)));

        let updatedCount = 0;

        // Iterate store messages and update matching ones
        for (const msgKey in this.store.messages) {
            const message = this.store.messages[msgKey];

            const msgAccountId = Array.isArray(message.account_id)
                ? message.account_id[0]
                : message.account_id;
            if (msgAccountId !== account_id) {
                continue;
            }

            const msgUid = String(message.uid ?? message.id);
            if (!uidSet.has(msgUid)) {
                continue;
            }

            const folderRec = this.store.folders?.[message.folder_id];
            const msgFolderName = folderRec?.imap_name || folderRec?.name;
            if (folder && msgFolderName && msgFolderName !== folder) {
                continue;
            }

            if (folder && !msgFolderName) {
                // Conservative: skip if folder metadata isn't loaded
                continue;
            }

            // Match found: update tags in-place (OWL reactive)
            // tags is array of {id, name, color} objects from backend
            message.tag_ids = tags || [];
            message.tags = tags || [];  // Both for compatibility


            updatedCount++;
        }

        if (updatedCount === 0) {
            // This is NORMAL - message might be in different folder or not loaded yet
            console.debug(
                `[Bus→Store] Messages not in current store (expected): ` +
                `account=${account_id}, folder=${folder}, uids=${uids.slice(0, 3)}` +
                (uids.length > 3 ? ` (+${uids.length - 3} more)` : "")
            );
        }
    }

    _refreshIfCurrentFolder({ account_id, folder, alsoMatch } = {}) {
        if (!this.store?.refreshMessages) {
            return;
        }
        if (this.store.currentAccountId !== account_id) {
            return;
        }
        if (!this.store.currentFolderId) {
            return;
        }
        if (!folder) {
            void this.store.refreshMessages();
            return;
        }
        const currentFolder = this.store.folders?.[this.store.currentFolderId];
        const currentFolderName = currentFolder?.imap_name || currentFolder?.name;
        if (!currentFolderName) {
            return;
        }
        if (folder === currentFolderName || alsoMatch === currentFolderName) {
            void this.store.refreshMessages();
        }
    }


    // POLLING LIFECYCLE (CONFIG-DRIVEN)


    /**
     * Start the polling heartbeat.
     * Respects configuration: enabled, interval, only_main_tab, pause_on_hidden
     */
    async startPolling() {
        if (this._pollInterval) {
            console.warn("[MailDesk Sync] Polling already active");
            return;
        }

        // Check if polling is enabled
        if (!this._config.enabled) {
            console.log("[MailDesk Sync] Polling disabled by configuration");
            return;
        }

        // Check multi-tab restriction
        if (
            this._config.only_main_tab &&
            this.multiTab &&
            !(await this.multiTab.isOnMainTab())
        ) {
            console.log("[MailDesk Sync] Polling skipped (not main tab)");
            return;
        }

        const intervalMs = this._config.interval_seconds * 1000;
        console.log(`[MailDesk Sync] Starting polling (${intervalMs}ms interval)`);

        // Setup visibility change listener
        if (this._config.pause_on_hidden) {
            document.addEventListener("visibilitychange", this._visibilityHandler);
        }

        // Initial poll
        this._poll();

        // Scheduled polling
        this._pollInterval = setInterval(() => {
            if (!this._isPaused) {
                this._poll();
            }
        }, intervalMs);
    }

    /**
     * Stop the polling heartbeat.
     */
    stopPolling() {
        if (this._pollInterval) {
            clearInterval(this._pollInterval);
            this._pollInterval = null;
            console.log("[MailDesk Sync] Polling stopped");
        }

        document.removeEventListener("visibilitychange", this._visibilityHandler);
        this._isPaused = false;
    }

    get isPolling() {
        return this._pollInterval !== null;
    }


    // VISIBILITY HANDLING


    _onVisibilityChange() {
        if (!this._config.pause_on_hidden) return;

        if (document.hidden) {
            this._isPaused = true;
            console.log("[MailDesk Sync] Polling paused (tab hidden)");
        } else {
            this._isPaused = false;
            console.log("[MailDesk Sync] Polling resumed (tab visible)");
            // Immediate poll on visibility restore
            this._poll();
        }
    }


    // POLL EXECUTION


    async _poll() {
        if (this._pollInFlight) {
            return;
        }

        const accounts = this.store?.accountsList || [];
        if (accounts.length === 0) {
            return;
        }

        this._pollInFlight = true;

        try {
            const result = await this.orm.call(
                "mailbox.account",
                "poll_mail_accounts",
                [],
                {}
            );

            if (result?.changes) {
                console.log("[MailDesk Sync] ✓ Poll result:", result);
            }
        } catch (err) {
            console.warn("[MailDesk Sync] Poll error (ignored):", err);
        } finally {
            this._pollInFlight = false;
        }
    }

    pollNow() {
        this._poll();
    }


    // NOTIFICATIONS


    _triggerNotifications(messages) {
        if (!this.notificationService) {
            console.warn("[MailDesk Sync] Notification service not available");
            return;
        }

        if (!Array.isArray(messages) || messages.length === 0) {
            return;
        }

        const count = this.notificationService.notifyBatch(messages);
        if (count > 0) {
            console.log(`[MailDesk Sync] Triggered ${count} notifications`);
        }
    }
}





export const maildeskSyncService = {
    dependencies: ["orm", "bus_service", "maildesk.store", "maildesk.notification", "multi_tab"],
    start(env, dependencies) {
        return new MailDeskSyncService(env, dependencies);
    },
};

registry.category("services").add("maildesk.sync", maildeskSyncService);
