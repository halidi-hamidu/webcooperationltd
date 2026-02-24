/** @odoo-module **/
// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/**
 * Tests for `static/src/js/services/maildesk_sync.esm.js`.
 *
 * Focus: bus payload application to store (flags_changed, unread_count_changed),
 * and poll guardrails (no polling without accounts / no concurrent polls).
 */

import { describe, test, expect } from "@odoo/hoot";

import { maildeskSyncService } from "../src/js/services/maildesk_sync.esm";

describe("MailDesk Sync Service", () => {
    test("flags_changed updates message is_read/is_starred", () => {
        const store = {
            messages: {
                "1|1|10": { id: 10, uid: "10", account_id: 1, folder_id: 1, is_read: false, is_starred: false },
            },
            folders: { 1: { id: 1, imap_name: "INBOX", name: "INBOX" } },
        };

        const service = maildeskSyncService.start({}, {
            orm: {},
            bus_service: {},
            "maildesk.store": store,
            "maildesk.notification": { notifyBatch: () => 0 },
            multi_tab: {},
        });

        service._applyFlagsChanged({
            account_id: 1,
            folder: "INBOX",
            index_ids: [10],
            uids: [],
            flags: { is_read: true, is_starred: true },
        });

        expect(store.messages["1|1|10"].is_read).toBe(true);
        expect(store.messages["1|1|10"].is_starred).toBe(true);
    });

    test("unread_count_changed is ignored in context mode (partner/search)", () => {
        const store = {
            partnerId: 10,
            searchQuery: "",
            findFolderId: () => 1,
            setFolderUnreadCount: () => {
                throw new Error("must not update in context mode");
            },
        };

        const service = maildeskSyncService.start({}, {
            orm: {},
            bus_service: {},
            "maildesk.store": store,
            "maildesk.notification": { notifyBatch: () => 0 },
            multi_tab: {},
        });

        service._applyUnreadCountChanged({ account_id: 1, folder: "INBOX", count: 5 });
        expect(true).toBe(true);
    });

    test("_poll does nothing when there are no accounts", async () => {
        const orm = { call: () => { throw new Error("must not call"); } };
        const store = { accountsList: [] };
        const service = maildeskSyncService.start({}, {
            orm,
            bus_service: {},
            "maildesk.store": store,
            "maildesk.notification": { notifyBatch: () => 0 },
            multi_tab: {},
        });
        await service._poll();
        expect(true).toBe(true);
    });

    test("_poll is single-flight (skips when in flight)", async () => {
        let calls = 0;
        const orm = { call: async () => { calls++; } };
        const store = { accountsList: [{ id: 1 }] };
        const service = maildeskSyncService.start({}, {
            orm,
            bus_service: {},
            "maildesk.store": store,
            "maildesk.notification": { notifyBatch: () => 0 },
            multi_tab: {},
        });
        service._pollInFlight = true;
        await service._poll();
        expect(calls).toBe(0);
    });
});
