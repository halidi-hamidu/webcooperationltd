// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk MailDesk Notification.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

/**
 * MailDesk Notification Service
 *
 * Handles browser notifications for new emails.
 *
 * Architecture:
 * - Domain event → notification (user-facing side effect)
 * - NO dependency on multi_tab (unreliable in SPA/iframe context)
 * - Per-tab deduplication (prevents spam)
 * - Independent of UI state (current folder, store, etc.)
 */
class MailDeskNotificationService {
    constructor(env, dependencies) {
        this.env = env;

        // Per-tab deduplication (prevents duplicate notifications in same tab)
        this._notifiedKeys = new Set();
        this._dedupTimeoutMs = 60000; // 1 minute dedup window

        // Sound configuration
        this._soundEnabled = true;
        this.sound = new Audio("/mail/static/src/audio/ting.mp3");

        // Window focus listener to clear dedup (user saw notifications)
        this._onFocus = () => this._clearDedup();
        window.addEventListener("focus", this._onFocus);
    }

    /**
     * Clean up on destroy.
     */
    destroy() {
        window.removeEventListener("focus", this._onFocus);
        this._notifiedKeys.clear();
    }

    /**
     * Notify about a new message.
     *
     * Architecture:
     * - Triggered directly from bus event payload (domain event)
     * - NO multi_tab gating (user-facing notifications must not be suppressed)
     * - Per-tab deduplication only
     *
     * @param {Object} dto - Message notification DTO
     * @returns {boolean} - Whether notification was shown
     */
    notify(dto) {
        // Permission check (browser API).
        if (!browser.Notification || browser.Notification.permission !== "granted") {
            console.warn("[MailDesk Notification] Browser notification permission not granted");
            return false;
        }

        // Build unique key for deduplication
        const key = this._buildKey(dto);

        // Per-tab deduplication.
        if (this._notifiedKeys.has(key)) {
            console.log(`[MailDesk Notification] Dedup: already notified ${key}`);
            return false;
        }

        // Extract notification content
        const subject = (dto.subject || dto.email_subject || dto.name || "").trim();
        if (!subject) {
            console.warn("[MailDesk Notification] No subject, skipping:", dto);
            return false;
        }

        const preview = (
            dto.preview_text ||
            dto.preview ||
            dto.snippet ||
            dto.body_preview ||
            dto.body_plain ||
            _t("You have a new email. Click to read.")
        ).trim();

        // Mark as notified (with auto-expire)
        this._notifiedKeys.add(key);
        setTimeout(() => {
            this._notifiedKeys.delete(key);
        }, this._dedupTimeoutMs);

        // Show notification + sound
        const deepLinkUrl = this._buildDeepLink(dto);
        this._showBrowserNotification(subject, preview, deepLinkUrl, dto);
        this._playSound();

        console.log(`[MailDesk Notification] Notified: ${key}`);
        return true;
    }

    /**
     * Notify about multiple messages in batch.
     *
     * @param {Array<Object>} dtos - Array of message DTOs
     * @returns {number} - Number of notifications shown
     */
    notifyBatch(dtos) {
        if (!Array.isArray(dtos) || dtos.length === 0) {
            return 0;
        }

        let count = 0;
        for (const dto of dtos) {
            if (this.notify(dto)) {
                count++;
            }
        }

        console.log(`[MailDesk Notification] Batch complete: ${count}/${dtos.length} shown`);
        return count;
    }

    /**
     * Build unique key for deduplication.
     * @private
     */
    _buildKey(dto) {
        const acc = Array.isArray(dto.account_id) ? dto.account_id[0] : dto.account_id;
        const fld = dto.folder_id || dto.folder;
        const id = dto.index_id || dto.message_id || dto.uid || dto.id;
        return `${acc || 'unknown'}|${fld || 'unknown'}|${id || 'unknown'}`;
    }

    /**
     * Build deep-link URL for notification click.
     * @private
     */
    _buildDeepLink(dto) {
        const base = "/maildesk";
        const params = new URLSearchParams();

        const acc = Array.isArray(dto.account_id) ? dto.account_id[0] : dto.account_id;
        if (acc) params.set("account", acc);
        if (dto.folder_id) params.set("folder", dto.folder_id);
        if (dto.id) params.set("message", dto.id);

        const query = params.toString();
        // Use hash (#) instead of query (?) for SPA deep linking
        return query ? `${base}#${query}` : base;
    }

    /**
     * Show browser notification popup with enriched information.
     *
     * Displays:
     * - Title: Subject
     * - Body: From, To Account, Preview
     *
     * @private
     */
    _showBrowserNotification(subject, preview, deepLinkUrl, dto = {}) {
        try {
            const tr = (text) => {
                try {
                    return String(_t(text));
                } catch {
                    return text;
                }
            };

            // Build sender display
            let fromDisplay = "";
            if (dto.sender_name && dto.from_email) {
                // Full display: "John Doe <john@example.com>"
                fromDisplay = `${dto.sender_name} <${dto.from_email}>`;
            } else if (dto.sender_name) {
                fromDisplay = dto.sender_name;
            } else if (dto.from_email) {
                fromDisplay = dto.from_email;
            } else {
                fromDisplay = tr("Unknown Sender");
            }

            // Build account display
            const accountDisplay = dto.account_display || tr("Mailbox");

            // Build notification title and body
            const title = `📬 ${subject}`;

            // Multi-line body with sender, account, and preview
            const bodyLines = [
                `💬 ${tr("Mailbox")}: ${accountDisplay}`,
                `👤 ${tr("From")}: ${fromDisplay}`,
                ``,
                preview.replace(/\s+/g, " ").substring(0, 200),
            ];
            const body = bodyLines.join("\n");

            const notification = new browser.Notification(title, {
                body,
                icon: "/maildesk_mail_client/static/description/icon.png",
                badge: "/maildesk_mail_client/static/description/icon.png",
                timestamp: Date.now(),
                requireInteraction: false, // Auto-dismiss after timeout
            });

            notification.onclick = () => {
                window.focus();
                window.open(deepLinkUrl, "_blank");
                notification.close();
            };
        } catch (error) {
            console.error("[MailDesk Notification] Failed to show notification:", error);
        }
    }

    /**
     * Play notification sound.
     * @private
     */
    async _playSound() {
        if (!this._soundEnabled) {
            return;
        }

        try {
            await this.sound.play();
        } catch {
            // Ignore audio play errors (autoplay restrictions)
        }
    }

    /**
     * Clear deduplication set (called on window focus).
     * @private
     */
    _clearDedup() {
        this._notifiedKeys.clear();
    }
}

export const maildeskNotificationService = {
    dependencies: [],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @param {Object} dependencies
     * @returns {MailDeskNotificationService}
     */
    start(env, dependencies) {
        return new MailDeskNotificationService(env, dependencies);
    },
};

registry.category("services").add("maildesk.notification", maildeskNotificationService);
