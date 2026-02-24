// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Composer Bubble.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { Component, useState, useRef } from "@odoo/owl";

/**
 * ComposerBubble - Folded state bubble for composer.
 * Pattern mirrored from Odoo Mail: chat_bubble.js
 *
 * Features:
 * - Circular bubble icon
 * - Hover shows preview dropdown (stable hover with delay)
 * - Click opens composer
 * - Close button removes composer (always clickable)
 */

export class ComposerBubble extends Component {
    static template = "maildesk_mail_client.ComposerBubble";
    static props = {
        composer: { type: Object },
        onClick: { type: Function },
        onClose: { type: Function },
    };

    setup() {
        this.rootRef = useRef("root");

        // Pattern mirrored from Odoo Mail ChatBubble: stable hover state
        // Uses a small delay on leave to prevent flicker when moving to preview
        this.hoverState = useState({
            isHovered: false,
        });

        this._leaveTimeout = null;
    }





    get composer() {
        return this.props.composer;
    }

    get isHovered() {
        return this.hoverState.isHovered;
    }

    get previewSubject() {
        return this.composer.subject || "(No subject)";
    }

    get previewRecipients() {
        return this.composer.previewRecipients;
    }

    /**
     * Get body preview with reliable fallback.
     * Uses ComposerRecord.body (synced from editor on every change).
     */
    get previewBody() {
        const html = this.composer.body;
        if (!html) return "(No content)";
        return this._stripHtml(html).slice(0, 150) || "(No content)";
    }

    get title() {
        return this.composer.title;
    }

    _stripHtml(html) {
        if (!html) return "";
        const div = document.createElement("div");
        div.innerHTML = html;
        return (div.textContent || div.innerText || "").trim();
    }


    // ACTIONS


    /**
     * Open composer window.
     * Pattern: click on bubble body opens window.
     */
    onClick = (ev) => {
        // Don't open if clicking close button
        if (ev.target.closest(".o-bubble-close")) return;
        ev.stopPropagation();
        this.props.onClick();
    };

    /**
     * Close composer.
     * Pattern: always clickable via t-on-click.stop.prevent.
     */
    onClose = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        this.props.onClose();
    };


    // HOVER — Pattern mirrored from Odoo Mail: ChatBubble
    // Uses delay on leave to allow moving mouse from bubble to preview.


    onMouseEnter = () => {
        // Cancel any pending leave
        if (this._leaveTimeout) {
            clearTimeout(this._leaveTimeout);
            this._leaveTimeout = null;
        }
        this.hoverState.isHovered = true;
    };

    onMouseLeave = () => {
        // Delay hide to allow mouse to move to preview
        this._leaveTimeout = setTimeout(() => {
            this.hoverState.isHovered = false;
            this._leaveTimeout = null;
        }, 150); // 150ms delay before hiding
    };

    /**
     * Called when mouse enters preview.
     * Keeps hover state alive.
     */
    onPreviewEnter = () => {
        if (this._leaveTimeout) {
            clearTimeout(this._leaveTimeout);
            this._leaveTimeout = null;
        }
        this.hoverState.isHovered = true;
    };

    /**
     * Called when mouse leaves preview.
     */
    onPreviewLeave = () => {
        this._leaveTimeout = setTimeout(() => {
            this.hoverState.isHovered = false;
            this._leaveTimeout = null;
        }, 150);
    };
}
