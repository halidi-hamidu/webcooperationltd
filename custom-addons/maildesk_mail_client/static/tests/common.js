/** @odoo-module **/
// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/**
 * MailDesk JS Test Helpers (Hoot)
 *
 * Small helper utilities for deterministic, side-effect-free unit tests.
 */

import { afterEach } from "@odoo/hoot";

const _restores = [];

/**
 * Patch a property and automatically restore it after each test.
 * @param {object} obj
 * @param {string} key
 * @param {any} value
 */
export function patch(obj, key, value) {
    const hadKey = Object.prototype.hasOwnProperty.call(obj, key);
    const previous = obj[key];
    obj[key] = value;
    _restores.push(() => {
        if (hadKey) {
            obj[key] = previous;
        } else {
            delete obj[key];
        }
    });
}

afterEach(() => {
    while (_restores.length) {
        _restores.pop()();
    }
});

export class FakeAudio {
    constructor() {
        this.playCalls = 0;
    }
    async play() {
        this.playCalls++;
    }
}
