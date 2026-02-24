// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk MailDesk Dom.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * maildesk_dom - Pure utility functions for DOM operations and formatting
 *
 * NO OWL dependencies (no hooks, no state).
 * Stateless helper functions.
 */

/**
 * Build a unique message key for deduplication and OWL keying.
 *
 * @param {Object} msg - Message object with account_id, folder_id, and uid/id
 * @returns {string} Composite key: "accountId|folderId|uid"
 */
export function buildMsgKey(msg) {
    const acc = Array.isArray(msg.account_id) ? msg.account_id[0] : msg.account_id;
    const fld = msg.folder_id;
    const uid = msg.uid ?? msg.id;
    return `${acc}|${fld}|${uid}`;
}

/**
 * Format a date string for user display.
 *
 * @param {string|Date} dateStr - ISO date string or Date object
 * @returns {string} Formatted date string
 */
export function formatUserDate(dateStr) {
    if (!dateStr) return "";
    try {
        const date = typeof dateStr === "string" ? new Date(dateStr) : dateStr;
        return date.toLocaleString(undefined, {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    } catch {
        return String(dateStr);
    }
}

/**
 * Normalize a message DTO for consistent frontend usage.
 *
 * @param {Object} msg - Raw message DTO from backend
 * @param {Function} markupFn - OWL markup function for HTML safety
 * @returns {Object} Normalized message
 */
export function normalizeMessage(msg, markupFn) {
    const normalized = { ...msg };

    if (msg.avatar_html !== undefined) {
        normalized.avatar_html = msg.avatar_html ? markupFn(msg.avatar_html) : "";
    }

    if (msg.uid != null) {
        normalized.uid = String(msg.uid);
    }

    if (msg.sort_ts != null) {
        const asInt = Number(msg.sort_ts);
        normalized.sort_ts = Number.isFinite(asInt) ? asInt : 0;
    }

    if (msg.sender_display_name !== undefined || msg.email_from !== undefined) {
        normalized.sender_display_name = msg.sender_display_name || msg.email_from || "";
    }

    if (msg.preview_text !== undefined) {
        normalized.preview_text = msg.preview_text || "";
    }

    // INVARIANT: formatted_date from backend is SSOT (context_timestamp)
    // NEVER use JS Date parsing - causes timezone mismatches
    if (msg.formatted_date !== undefined) {
        normalized.formatted_date = msg.formatted_date;
    }
    // Log warning if date exists but formatted_date missing
    if (msg.date && !normalized.formatted_date) {
        console.warn("[DATE] Missing formatted_date for message, date=", msg.date);
    }

    normalized.msg_key = msg.msg_key || buildMsgKey(msg);

    // CRITICAL: Ensure body_original is set for ThreadMessage iframe rendering
    // Backend should provide body_original, but fallback to body_html if missing
    if (!normalized.body_original && normalized.body_html) {
        normalized.body_original = normalized.body_html;
    }

    return normalized;
}
