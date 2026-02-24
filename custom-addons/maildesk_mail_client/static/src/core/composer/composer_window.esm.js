// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Composer Window.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { Component, markup, useState, useRef, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { ComposerInput } from "./composer_input.esm.js";
import { ComposerBubble } from "./composer_bubble.esm.js";

/**
 * ComposerWindow - Window shell for a single composer.
 * Pattern mirrored from Odoo Mail: chat_window.js
 *
 * Features:
 * - Draggable via header (pattern: useMovable equivalent)
 * - Resizable (width/height)
 * - Fullscreen toggle
 * - Fold to bubble
 * - State stored in ComposerRecord
 */

export class ComposerWindow extends Component {
    static template = "maildesk_mail_client.ComposerWindow";
    static components = { ComposerInput, ComposerBubble };
    static props = {
        composer: { type: Object },
        onDragStart: { type: Function },
        onDragEnd: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.composerService = useService("maildesk.composer");
        this.notification = useService("notification");

        // Refs for drag and resize
        this.rootRef = useRef("root");
        this.headerRef = useRef("header");

        // Local UI state for drag/resize operations
        this.dragState = useState({
            isDragging: false,
            isResizing: false,
            resizeDir: null, // 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
        });

        // Load initial data for reply/forward/draft modes
        onWillStart(async () => {
            await this._loadInitialData();
        });

        onMounted(() => {
            // Set initial position if not set
            if (this.composer.position.top === null) {
                this._setInitialPosition();
            }
        });
    }





    get composer() {
        return this.props.composer;
    }

    get isFolded() {
        return this.composer.folded;
    }

    get isFullscreen() {
        return this.composer.isFullscreen;
    }

    get title() {
        return this.composer.title;
    }

    /**
     * Get inline style for window positioning and sizing.
     * Pattern mirrored from Odoo Mail: ChatWindow uses inline styles for position.
     */
    get windowStyle() {
        if (this.isFullscreen) {
            return {
                position: "fixed",
                top: "0",
                left: "0",
                width: "100vw",
                height: "100vh",
                maxHeight: "100vh",
                borderRadius: "0",
                zIndex: "1060",
            };
        }

        const { top, left } = this.composer.position;
        const { width, height } = this.composer.size;

        const style = {
            width: `${width}px`,
            height: this.isFolded ? "auto" : `${height}px`,
        };

        // If position is set, use absolute positioning
        if (top !== null && left !== null) {
            style.position = "fixed";
            style.top = `${top}px`;
            style.left = `${left}px`;
            style.bottom = "auto";
            style.right = "auto";
        }

        return style;
    }

    get windowStyleStr() {
        return Object.entries(this.windowStyle)
            .map(([k, v]) => `${k.replace(/([A-Z])/g, "-$1").toLowerCase()}: ${v}`)
            .join("; ");
    }


    // ACTIONS


    toggleFold = () => {
        this.composer.toggleFold();
    };

    toggleFullscreen = () => {
        this.composer.toggleFullscreen();
    };

    close = () => {
        this.composerService.closeComposer(this.composer.id);
    };

    onBubbleClick = () => {
        this.composer.open();
    };


    // DRAG — Pattern mirrored from Odoo Mail: useMovable


    onHeaderMouseDown = (ev) => {
        // Only left click
        if (ev.button !== 0) return;
        // Don't drag in fullscreen
        if (this.isFullscreen) return;

        ev.preventDefault();
        ev.stopPropagation();

        this._startX = ev.clientX;
        this._startY = ev.clientY;
        this._startPos = { ...this.composer.position };

        // If position not set, get from element
        if (this._startPos.top === null) {
            const rect = this.rootRef.el.getBoundingClientRect();
            this._startPos = { top: rect.top, left: rect.left };
            this.composer.savePosition(this._startPos);
        }

        // DRAG THRESHOLD implementation
        // We only start the global overlay drag if the user moves > 3px.
        // This allows 'click' and 'dblclick' to bubble on the header normally
        // without the overlay intercepting the mouseup.

        const threshold = 3;

        const onMove = (moveEv) => {
            const dx = moveEv.clientX - this._startX;
            const dy = moveEv.clientY - this._startY;
            if (Math.abs(dx) > threshold || Math.abs(dy) > threshold) {
                // Threshold exceeded: Start real drag
                cleanup();
                this.dragState.isDragging = true;
                this.props.onDragStart(this.composer.id, this._handleDragEvent.bind(this));
            }
        };

        const onUp = () => {
            // Mouse released before threshold: It's a click!
            cleanup();
            // No drag started, no overlay shown.
        };

        const cleanup = () => {
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
        };

        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    };


    // RESIZE — Pattern mirrored from Odoo Mail: ChatWindow resize handles


    onResizeMouseDown = (ev, dir) => {
        if (ev.button !== 0) return;
        if (this.isFullscreen) return;

        ev.preventDefault();
        ev.stopPropagation();

        this.dragState.isResizing = true;
        this.dragState.resizeDir = dir;
        this._startX = ev.clientX;
        this._startY = ev.clientY;
        this._startSize = { ...this.composer.size };
        this._startPos = { ...this.composer.position };

        // Delegate to container specific handler
        this.props.onDragStart(this.composer.id, this._handleDragEvent.bind(this));
    };

    /**
     * Unified handler called by ComposerContainer's global overlay
     * @param {MouseEvent} ev
     * @param {'mousemove'|'mouseup'} type
     */
    _handleDragEvent(ev, type) {
        if (type === "mouseup") {
            this._onMouseUp();
            return;
        }

        if (this.dragState.isDragging) {
            const dx = ev.clientX - this._startX;
            const dy = ev.clientY - this._startY;
            this.composer.savePosition({
                top: this._startPos.top + dy,
                left: this._startPos.left + dx,
            });
        } else if (this.dragState.isResizing) {
            const dx = ev.clientX - this._startX;
            const dy = ev.clientY - this._startY;
            const dir = this.dragState.resizeDir;

            let newWidth = this._startSize.width;
            let newHeight = this._startSize.height;
            let newTop = this._startPos.top;
            let newLeft = this._startPos.left;

            // 1. Calculate new dimensions based on direction
            if (dir.includes("e")) {
                newWidth = this._startSize.width + dx;
            }
            if (dir.includes("w")) {
                newWidth = this._startSize.width - dx;
                // Defer left update to after clamping
            }
            if (dir.includes("s")) {
                newHeight = this._startSize.height + dy;
            }
            if (dir.includes("n")) {
                newHeight = this._startSize.height - dy;
                newTop = this._startPos.top + dy;
            }

            // 2. Apply Size (Clamped internally by ComposerRecord)
            this.composer.saveSize({ width: newWidth, height: newHeight });

            // 3. Fix A: Geometry Correctness
            // For West/North-West resize, we must update 'left' based on the
            // ACTUAL applied width delta (after clamping), not the raw mouse delta.
            if (dir.includes("w")) {
                const appliedWidth = this.composer.size.width;
                const deltaWidth = appliedWidth - this._startSize.width;
                newLeft = this._startPos.left - deltaWidth;
            }

            // 4. Update Position
            if (dir.includes("n") || dir.includes("w")) {
                this.composer.savePosition({ top: newTop, left: newLeft });
            }
        }
    }

    _onMouseUp() {
        this.dragState.isDragging = false;
        this.dragState.isResizing = false;
        this.dragState.resizeDir = null;
        // Container handles event removal
    }


    // INITIAL POSITION


    _setInitialPosition() {
        // Position at bottom-right, offset by index
        const index = this.composerService.composers.findIndex(c => c.id === this.composer.id);
        const { width } = this.composer.size;
        const gap = 16;
        const rightOffset = (width + gap) * index + gap;

        this.composer.savePosition({
            top: window.innerHeight - 700,
            left: window.innerWidth - rightOffset - width,
        });
    }


    // DATA LOADING


    async _loadInitialData() {
        const c = this.composer;

        // FIX: State Preservation
        // If data is already initialized (e.g. re-mount after attachment upload),
        // DO NOT overwrite user's current state (accountId, body changes).
        if (c._isInitialized) {
            return;
        }

        // Load accounts if not provided
        if (!c.accounts || c.accounts.length === 0) {
            try {
                const accounts = await this.orm.searchRead(
                    "mailbox.account",
                    [["access_user_ids", "in", [user.userId]]],
                    ["id", "name", "email", "sender_name"]
                );
                c.accounts = accounts;
                if (accounts.length && !c.accountId) {
                    c.accountId = accounts[0].id;
                    c.fromDisplay = accounts[0].sender_name || accounts[0].name || "";
                }
            } catch (e) {
                console.error("Failed to load accounts:", e);
            }
        }

        // Load message data for reply/forward/draft
        if (c.msgKey && c.mode !== "new") {
            try {
                if (c.mode === "draft") {
                    // Extract ID from composite key (e.g. "1|1066|draft|63" -> 63)
                    // The backend expects a pure integer ID, not the frontend composite key.
                    let draftId = c.msgKey;
                    if (typeof draftId === "string" && draftId.includes("|")) {
                        draftId = parseInt(draftId.split("|").pop());
                    }
                    const data = await this.orm.call("mailbox.sync", "load_draft", [draftId]);
                    this._applyDraftData(data);
                } else {
                    const method = c.mode === "forward" ? "prepare_forward" : "prepare_reply";
                    const kwargs = c.mode === "forward" ? {} : { reply_all: c.mode === "replyAll" };
                    const data = await this.orm.call("maildesk.ui_cache", method, [c.msgKey], kwargs);
                    this._applyReplyData(data);
                }
            } catch (e) {
                console.error("Failed to load composer data:", e);
            }
        }
        // 3. Ensure Signature is Loaded (SSOT)
        // In Reply/Forward, accountId comes from backend but signature might be missing.
        // We must ensure it's loaded exactly once.
        if (c.accountId && c.signatureHtml === undefined) {
            try {
                const res = await this.orm.searchRead(
                    "mailbox.account",
                    [["id", "=", c.accountId]],
                    ["signature"]
                );
                c.signatureHtml = res?.[0]?.signature || "";
            } catch (e) {
                console.error("Failed to load signature:", e);
                c.signatureHtml = ""; // Fallback to empty to prevent loops
            }
        }

        c._isInitialized = true;
    }

    _applyDraftData(data) {
        const c = this.composer;
        c.subject = data.subject || "";
        c.body = data.body_html || "";
        c.to = (data.to || []).map(e => ({ email: e }));
        c.cc = (data.cc || []).map(e => ({ email: e }));
        c.bcc = (data.bcc || []).map(e => ({ email: e }));
        c.showCc = c.cc.length > 0;
        c.showBcc = c.bcc.length > 0;
        c.attachments = (data.attachments || []).map(a => ({ id: a.id, name: a.name, mimetype: a.mimetype }));
        // PRESERVATION: Only set account if not already set by user/defaults
        if (!c.accountId) {
            c.accountId = data.account_id;
        }
        c.draftMessageId = c.msgKey;
        c.requestReadReceipt = !!data.request_read_receipt;
        c.requestDeliveryReceipt = !!data.request_delivery_receipt;
        if (!c.fromDisplay) {
            c.fromDisplay = data.from_display || "";
        }
    }

    _applyReplyData(data) {
        const c = this.composer;
        c.subject = data.subject || "";
        c.body = data.body_html || "";
        c.to = (data.to || []).map(e => ({ email: e }));
        c.cc = (data.cc || []).map(e => ({ email: e }));
        c.bcc = (data.bcc || []).map(e => ({ email: e }));
        c.showCc = c.cc.length > 0;
        c.showBcc = c.bcc.length > 0;
        c.attachments = (data.attachments || []).map(a => ({ id: a.id, name: a.name, mimetype: a.mimetype, access_token: a.access_token || "" }));
        // PRESERVATION: Only set account if not already set by user/defaults
        if (!c.accountId) {
            c.accountId = data.account_id;
        }
        if (!c.fromDisplay) {
            c.fromDisplay = data.from_display || "";
        }
        c.replyToMsg = c.msgKey;
    }
}
