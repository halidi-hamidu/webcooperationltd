/** @odoo-module **/
// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/**
 * Tests for `static/src/js/services/maildesk_store.esm.js`.
 *
 * Focus: deterministic store mutations for messages.
 */

import { describe, test, expect } from "@odoo/hoot";

import { maildeskStoreService } from "../src/js/services/maildesk_store.esm";
import { FileModel } from "@web/core/file_viewer/file_model";

describe("MailDesk Store Service", () => {
    test("upsertMessage inserts then merges updates", () => {
        const store = maildeskStoreService.start({});

        const m1 = store.upsertMessage("1|1|10", { id: 10, account_id: 1, folder_id: 1, uid: "10", subject: "A" });
        expect(m1.subject).toBe("A");

        const m2 = store.upsertMessage("1|1|10", { subject: "B" });
        expect(store.messages["1|1|10"].subject).toBe("B");
    });

    test("deleteMessage clears selection when deleting selected key", () => {
        const store = maildeskStoreService.start({});
        store.upsertMessage("1|1|10", { id: 10, account_id: 1, folder_id: 1, uid: "10", subject: "A" });
        store.selectedMsgKey = "1|1|10";
        store.selectedMsgKeys = ["1|1|10"];

        store.deleteMessage("1|1|10");
        expect(store.selectedMsgKey).toBe(null);
        expect(store.selectedMsgKeys).toEqual([]);
    });

    test("binary attachments are wrapped into FileModel contract", () => {
        const store = maildeskStoreService.start({});
        const msgKey = "1|1|10";

        store.upsertMessage(msgKey, {
            id: 10,
            account_id: 1,
            folder_id: 1,
            uid: "10",
            subject: "A",
            attachments: [
                {
                    id: 123,
                    name: "a.png",
                    filename: "a.png",
                    mimetype: "image/png",
                    type: "binary",
                    access_token: "tok",
                    checksum: "chk",
                    // Legacy fields that used to be sent by backend; should not break wrapping.
                    defaultSource: "/web/content/123?access_token=tok",
                    downloadUrl: "/web/content/123?download=true&access_token=tok",
                },
            ],
        });

        const att = store.messages[msgKey].attachments[0];
        expect(att instanceof FileModel).toBe(true);
        expect(att.urlRoute).toBe("/web/image/123");
        expect(att.defaultSource).toContain("/web/image/123");
        expect(att.defaultSource).toContain("access_token=tok");
        expect(att.downloadUrl).toContain("download=true");
    });

    test("url attachments stay plain objects for AttachmentList link rendering", () => {
        const store = maildeskStoreService.start({});
        const msgKey = "1|1|10";

        store.upsertMessage(msgKey, {
            id: 10,
            account_id: 1,
            folder_id: 1,
            uid: "10",
            subject: "A",
            attachments: [{ id: "ext-1", name: "Link", type: "url", url: "https://example.com" }],
        });

        const att = store.messages[msgKey].attachments[0];
        expect(att instanceof FileModel).toBe(false);
        expect(att.type).toBe("url");
        expect(att.url).toBe("https://example.com");
        expect(att.isViewable).toBe(false);
    });
});
