// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Composer Record.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * ComposerRecord - Record-style class for Composer state.
 * Pattern mirrored from Odoo Mail: chat_window_model.js
 *
 * This class owns ALL state for a single composer window:
 * - Draft data (subject, body, recipients, attachments)
 * - UI state (folded, fullscreen, position, size)
 * - Lifecycle (status, callbacks)
 */

let _composerId = 0;

// Pattern mirrored from Odoo Mail: ChatWindow default dimensions
const DEFAULT_WIDTH = 470;
const DEFAULT_HEIGHT = 700;
const MIN_WIDTH = 300;
const MIN_HEIGHT = 300;
const MAX_WIDTH = 800;
const MAX_HEIGHT = 800;

export class ComposerRecord {
    /**
     * @param {Object} params - Initial parameters
     */
    constructor(params = {}) {

        // IDENTITY

        this.id = ++_composerId;
        this.mode = params.mode || "new"; // 'new' | 'reply' | 'replyAll' | 'forward' | 'draft'
        this.msgKey = params.msgKey || null;


        // DRAFT DATA

        this.subject = params.subject || "";
        this.body = params.body || "";
        this.to = params.to || [];
        this.cc = params.cc || [];
        this.bcc = params.bcc || [];
        this.showCc = params.showCc || this.cc.length > 0;
        this.showBcc = params.showBcc || this.bcc.length > 0;
        this.attachments = params.attachments || [];
        this.accountId = params.accountId || null;
        this.accounts = params.accounts || [];
        this.fromDisplay = params.fromDisplay || "";
        this.draftMessageId = params.draftMessageId || null;
        this.replyToMsg = params.replyToMsg || null;
        this.requestReadReceipt = params.requestReadReceipt || false;
        this.requestDeliveryReceipt = params.requestDeliveryReceipt || false;


        // THREADING CONTEXT (for replies)

        this.replyToMessageId = params.replyToMessageId || "";  // Parent's RFC Message-ID
        this.originalReferences = params.originalReferences || "";  // Parent's References header
        this.threadId = params.threadId || "";  // Provider-native thread ID (Gmail/Outlook)
        this.originalMessageId = params.originalMessageId || "";  // For forward reference


        // ODOO LINKAGE (inherited from parent)

        this.model = params.model || null;
        this.resId = params.resId || null;


        // UI STATE — Pattern mirrored from Odoo Mail: ChatWindow

        this.folded = params.folded || false;
        this.isFullscreen = params.isFullscreen || false;
        this.isActive = true;

        // Position (stored for drag persistence)
        // Pattern mirrored from Odoo Mail: ChatWindow uses position for movable
        this.position = params.position || { top: null, left: null };

        // Size (stored for resize persistence)
        this.size = params.size || { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT };

        // Previous state for fullscreen restore
        this._prevPosition = null;
        this._prevSize = null;


        // LIFECYCLE

        this.status = "draft"; // 'draft' | 'sending' | 'sent' | 'error'
        this.error = null;

        // Callbacks
        this._onSent = params.onSent || null;
        this._onClose = null;

        // Editor reference (set by UI component)
        this.wysiwygEditor = null;

        // Guard for strict one-time signature insertion
        this._signatureInserted = false;
    }


    // ALIASES (for EmailInputField compatibility)


    get To() { return this.to; }
    set To(val) { this.to = val; }

    get Cc() { return this.cc; }
    set Cc(val) { this.cc = val; }

    get Bcc() { return this.bcc; }
    set Bcc(val) { this.bcc = val; }


    // STATIC CONSTRAINTS


    static get MIN_WIDTH() { return MIN_WIDTH; }
    static get MIN_HEIGHT() { return MIN_HEIGHT; }
    static get MAX_WIDTH() { return MAX_WIDTH; }
    static get MAX_HEIGHT() { return MAX_HEIGHT; }
    static get DEFAULT_WIDTH() { return DEFAULT_WIDTH; }
    static get DEFAULT_HEIGHT() { return DEFAULT_HEIGHT; }


    // UI STATE METHODS — Pattern mirrored from Odoo Mail: ChatWindow


    /**
     * Fold/minimize the composer (shows bubble).
     */
    fold() {
        this.folded = true;
    }

    /**
     * Expand/open the composer window.
     */
    open() {
        this.folded = false;
    }

    /**
     * Toggle fold state.
     */
    toggleFold() {
        this.folded = !this.folded;
    }

    /**
     * Toggle fullscreen mode.
     * Pattern mirrored from Odoo Mail: ChatWindow expand behavior.
     */
    toggleFullscreen() {
        if (this.isFullscreen) {
            // Restore previous position and size
            if (this._prevPosition) {
                this.position = { ...this._prevPosition };
            }
            if (this._prevSize) {
                this.size = { ...this._prevSize };
            }
            this.isFullscreen = false;
        } else {
            // Save current position and size
            this._prevPosition = { ...this.position };
            this._prevSize = { ...this.size };
            this.isFullscreen = true;
        }
    }

    /**
     * Save position after drag.
     * @param {{top: number, left: number}} pos
     */
    savePosition(pos) {
        this.position = { ...pos };
    }

    /**
     * Save size after resize.
     * @param {{width: number, height: number}} size
     */
    saveSize(size) {
        // Clamp to min/max
        this.size = {
            width: Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, size.width)),
            height: Math.max(MIN_HEIGHT, Math.min(MAX_HEIGHT, size.height)),
        };
    }


    // DRAFT DATA METHODS


    toggleCc() {
        this.showCc = !this.showCc;
        if (!this.showCc) {
            this.cc = [];
        }
    }

    toggleBcc() {
        this.showBcc = !this.showBcc;
        if (!this.showBcc) {
            this.bcc = [];
        }
    }

    addRecipient(entry, field) {
        const list = this[field];
        if (!list.some(e => e.email === entry.email)) {
            this[field] = [...list, entry];
        }
    }

    removeRecipient(email, field) {
        this[field] = this[field].filter(e => e.email !== email);
    }

    addAttachment(attachment) {
        this.attachments = [...this.attachments, attachment];
    }

    removeAttachment(id) {
        this.attachments = this.attachments.filter(a => a.id !== id);
    }


    // PREVIEW GETTERS (For folded bubble state)


    /**
     * Get preview text for bubble hover.
     */
    get previewText() {
        const toStr = this.to.length > 0 ? this.to[0].email : "(No recipient)";
        const subjectStr = this.subject || "(No subject)";
        const bodyText = this._stripHtml(this.body).slice(0, 50);
        return `To: ${toStr} — ${subjectStr}${bodyText ? " — " + bodyText : ""}`;
    }

    /**
     * Get subject for bubble preview.
     */
    get previewSubject() {
        return this.subject || "(No subject)";
    }

    /**
     * Get body snippet for bubble preview.
     */
    get previewBody() {
        return this._stripHtml(this.body).slice(0, 100) || "(No content)";
    }

    /**
     * Get recipients string for bubble preview.
     */
    get previewRecipients() {
        if (this.to.length === 0) return "(No recipient)";
        if (this.to.length === 1) return this.to[0].email;
        return `${this.to[0].email} +${this.to.length - 1}`;
    }

    /**
     * Get title for window header.
     */
    get title() {
        switch (this.mode) {
            case "reply":
                return "Reply";
            case "replyAll":
                return "Reply All";
            case "forward":
                return "Forward";
            case "draft":
                return "Draft";
            default:
                return "New Message";
        }
    }

    _stripHtml(html) {
        if (!html) return "";
        const div = document.createElement("div");
        div.innerHTML = html;
        return div.textContent || div.innerText || "";
    }


    // SERIALIZATION


    getDraftPayload() {
        return {
            draft_id: this.draftMessageId,
            account_id: this.accountId,
            subject: this.subject.trim(),
            body_html: this.body,
            to_emails: this.to.map(e => e.email).join(","),
            cc_emails: this.cc.map(e => e.email).join(","),
            bcc_emails: this.bcc.map(e => e.email).join(","),
            attachment_ids: this.attachments.map(a => a.id),
            request_read_receipt: this.requestReadReceipt,
            request_delivery_receipt: this.requestDeliveryReceipt,
            from_display: this.fromDisplay,
        };
    }

    getSendPayload() {
        const clean = (arr) =>
            (arr || [])
                .map(e => (typeof e === "string" ? e : e?.email))
                .filter(v => !!v)
                .map(v => v.trim());

        return {
            account_id: this.accountId,
            subject: this.subject.trim(),
            body_html: this.body,
            to_emails: clean(this.to),
            cc_emails: clean(this.cc),
            bcc_emails: clean(this.bcc),
            attachment_ids: this.attachments.map(a => a.id),
            request_read_receipt: this.requestReadReceipt,
            request_delivery_receipt: this.requestDeliveryReceipt,
            from_display: this.fromDisplay,
            draft_id: this.draftMessageId,
            // THREADING: These enable In-Reply-To and References headers
            reply_to_message_id: this.replyToMessageId || null,
            original_references: this.originalReferences || null,
            thread_id: this.threadId || null,
            // ODOO LINKAGE: Link reply to same document as parent
            model: this.model || null,
            res_id: this.resId || null,
        };
    }
}
