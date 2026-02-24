// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Composer Container.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ComposerWindow } from "./composer_window.esm.js";

/**
 * ComposerContainer - Global Hub for Composer Windows.
 * Pattern mirrored from Odoo Mail: odoo/addons/mail/static/src/core/common/chat_hub.js
 *
 * This component:
 * - Is mounted at Shell level via registry.category("main_components")
 * - Survives navigation (action changes)
 * - Renders ALL active composer windows from the composer service
 */

export class ComposerContainer extends Component {
    static template = "maildesk_mail_client.ComposerContainer";
    static components = { ComposerWindow };
    static props = {};

    setup() {
        // Pattern mirrored from Odoo Mail: useService for global store access
        this.composerService = useState(useService("maildesk.composer"));
        this.dragState = useState({
            activeComposerId: null,
            handler: null, // Callback function from the active window
        });
    }

    /**
     * Get all active composers from the service.
     * @returns {import('./composer_record.esm.js').ComposerRecord[]}
     */
    get composers() {
        return this.composerService.composers || [];
    }

    onDragStart(composerId, handler) {
        this.dragState.activeComposerId = composerId;
        this.dragState.handler = handler;
    }

    onDragEnd() {
        this.dragState.activeComposerId = null;
        this.dragState.handler = null;
    }

    _onMouseMove(ev) {
        if (this.dragState.handler) {
            this.dragState.handler(ev, "mousemove");
        }
    }

    _onMouseUp(ev) {
        if (this.dragState.handler) {
            this.dragState.handler(ev, "mouseup");
            this.onDragEnd();
        }
    }
}
