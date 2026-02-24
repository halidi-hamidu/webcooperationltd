// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Composer Service.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ComposerRecord } from "./composer_record.esm.js";

/**
 * Composer Service - Global store for composer windows.
 * Pattern mirrored from Odoo Mail: odoo/addons/mail/static/src/core/common/chat_window_service.js
 *
 * This service manages the lifecycle of all composer windows.
 * It survives navigation because services persist across route changes.
 *
 * CRITICAL: Service is wrapped with reactive() so that useState(useService(...))
 * in components can track changes. This is the canonical Odoo pattern.
 */

class ComposerService {
    constructor() {
        /**
         * @type {ComposerRecord[]}
         * Array of active composer records.
         */
        this.composers = [];
    }


    // PUBLIC API


    /**
     * Open a new composer window.
     * @param {Object} params - ComposerRecord constructor params
     * @returns {ComposerRecord} The created composer
     */
    openComposer(params = {}) {
        const composer = new ComposerRecord(params);
        // Mutate in place - reactive() will track this
        this.composers.push(composer);
        return composer;
    }

    /**
     * Close a composer by ID.
     * @param {number} composerId
     */
    closeComposer(composerId) {
        const idx = this.composers.findIndex(c => c.id === composerId);
        if (idx !== -1) {
            this.composers[idx].isActive = false;
            this.composers.splice(idx, 1);
        }
    }

    /**
     * Get all active composers.
     * @returns {ComposerRecord[]}
     */
    getComposers() {
        return this.composers;
    }

    /**
     * Get a specific composer by ID.
     * @param {number} composerId
     * @returns {ComposerRecord|undefined}
     */
    getComposer(composerId) {
        return this.composers.find(c => c.id === composerId);
    }

    /**
     * Check if any composer is open.
     * @returns {boolean}
     */
    hasOpenComposers() {
        return this.composers.length > 0;
    }
}



// Pattern mirrored from Odoo Mail: service returns reactive() wrapped instance


export const composerService = {
    dependencies: [],
    /**
     * @param {import("@web/env").OdooEnv} env
     * @returns {ComposerService}
     */
    start(env) {
        // CRITICAL: Wrap with reactive() so useState(useService(...)) works
        return reactive(new ComposerService());
    },
};

registry.category("services").add("maildesk.composer", composerService);
