/** @odoo-module **/
// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/**
 * Tests for `static/src/js/services/maildesk_notification.esm.js`.
 *
 * Focus: notification permission gating + per-tab deduplication.
 */

import { describe, test, expect } from "@odoo/hoot";
import { browser } from "@web/core/browser/browser";

import { maildeskNotificationService } from "../src/js/services/maildesk_notification.esm";
import { FakeAudio, patch } from "./common";

describe("MailDesk Notification Service", () => {
    test("returns false when browser permission is not granted", () => {
        patch(window, "Audio", FakeAudio);

        class FakeNotificationDenied { }
        FakeNotificationDenied.permission = "denied";
        patch(browser, "Notification", FakeNotificationDenied);

        const service = maildeskNotificationService.start({}, {});
        try {
            const ok = service.notify({ subject: "Hello", account_id: 1, folder_id: 1, id: 10 });
            expect(ok).toBe(false);
        } finally {
            service.destroy();
        }
    });

    test("deduplicates notifications per tab", () => {
        patch(window, "Audio", FakeAudio);

        const created = [];
        class FakeNotification {
            constructor(title, opts) {
                created.push({ title, opts });
                this.onclick = null;
            }
            close() { }
        }
        FakeNotification.permission = "granted";
        patch(browser, "Notification", FakeNotification);
        patch(window, "open", () => { });
        patch(window, "focus", () => { });

        const service = maildeskNotificationService.start({}, {});
        try {
            const dto = { subject: "Hello", account_id: 1, folder_id: 1, id: 10, preview: "Preview" };
            expect(service.notify(dto)).toBe(true);
            expect(service.notify(dto)).toBe(false);
            expect(created.length).toBe(1);
        } finally {
            service.destroy();
        }
    });
});
