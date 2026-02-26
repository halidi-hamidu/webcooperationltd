// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Mail Detail.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * MailDetail Component
 *
 * Renders the message detail view with iframe for HTML body, attachments, and actions.
 * Uses maildeskStore for reactive state management.
 */

import { Component, useState, useRef, onMounted, onWillUnmount, onWillRender } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { AttachmentList } from "@mail/core/common/attachment_list";
import { generateIframeSrcdoc, getIframeSandbox } from "../../../utils/maildesk_iframe.esm.js";
import { PartnerCardPopover } from "../../popovers/partner_card/partner_card_popover.esm.js";
import { ThreadContainer } from "../thread_container/thread_container.esm.js";

export class MailDetail extends Component {
    static template = "maildesk_mail_client.MailDetailComponent";
    static components = { AttachmentList, ThreadContainer };
    static props = {
        message: { optional: true },
    };

    setup() {
        this.notification = useService("notification");
        this.action = useService("action");
        this.maildeskStore = useState(useService("maildesk.store"));
        this.fileViewer = useFileViewer();
        this.partnerCard = usePopover(PartnerCardPopover);
        this.iframeRef = useRef("iframe");

        // State for iframe content (derived from store)
        this.state = useState({
            iframeSrcdoc: "",
            isLoadingMessage: false,
            lastBodyOriginal: null,  // Track for change detection
            lastMsgKey: null,        // Track for thread fetch
        });

        // Handle postMessage from iframe
        // Handle postMessage from iframe
        this.messageHandler = (ev) => {
            // SOURCE VALIDATION: Only accept messages from the current active iframe
            if (ev.source !== this.iframeRef.el?.contentWindow) {
                return;
            }

            if (ev.data?.type === "maildesk-link-click" && ev.data.href) {
                window.open(ev.data.href, "_blank", "noopener,noreferrer");
            }
            if (ev.data?.type === "maildesk-iframe-height" && ev.data.height) {
                this.resizeIframe(ev.data.height);
            }
        };

        onMounted(() => {
            window.addEventListener("message", this.messageHandler);
            this.updateIframeSrcdoc();
        });

        onWillUnmount(() => {
            window.removeEventListener("message", this.messageHandler);
        });

        // Watch for selectedMessage.body_original changes on every render
        // This handles async body_original loading via in-place mutations
        onWillRender(() => {
            const msg = this.maildeskStore.selectedMessage;
            const body = msg?.body_original;
            if (body !== this.state.lastBodyOriginal) {
                this.state.lastBodyOriginal = body;
                // Schedule iframe update after this render cycle
                Promise.resolve().then(() => this.updateIframeSrcdoc());
            }

            // Fetch thread if new message with thread_id
            if (msg?.msg_key && msg.msg_key !== this.state.lastMsgKey) {
                this.state.lastMsgKey = msg.msg_key;
                if (msg.thread_id) {
                    this.maildeskStore.fetchThread?.(msg.thread_id, msg.account_id?.[0]);
                }
            }
        });
    }

    // Getters

    // Getter reads from store for reactivity
    get selectedMessage() {
        return this.maildeskStore.selectedMessage;
    }

    get hasMessage() {
        return !!this.maildeskStore.selectedMessage;
    }

    get iframeSandbox() {
        const msg = this.maildeskStore.selectedMessage;
        return getIframeSandbox(msg?.force_show_content || msg?.content_trusted);
    }

    get folderName() {
        const msg = this.selectedMessage;
        if (!msg || !msg.folder_id) return "";
        const folder = this.maildeskStore.folders?.[msg.folder_id];
        return folder ? folder.name : "";
    }

    get mailboxName() {
        const msg = this.selectedMessage;
        if (!msg) return "";
        let accountId = msg.account_id;
        if (Array.isArray(accountId)) accountId = accountId[0];
        if (!accountId) return "";
        const account = this.maildeskStore.accounts?.[accountId];
        return account ? (account.sender_name || account.name || "") : "";
    }

    get isSentFolder() {
        return this.selectedMessage?.folder_type === "sent";
    }

    get mailboxEmail() {
        const msg = this.selectedMessage;
        if (!msg) return "";
        let accountId = msg.account_id;
        if (Array.isArray(accountId)) accountId = accountId[0];
        if (!accountId) return "";
        const account = this.maildeskStore.accounts?.[accountId];
        return account?.email || "";
    }

    get attachmentsForAttachmentList() {
        const atts = this.selectedMessage?.attachments || [];
        // Deduplicate by id to prevent Owl "duplicate key" errors
        const seen = new Set();
        const unique = atts.filter(a => {
            if (!a?.id || seen.has(a.id)) return false;
            seen.add(a.id);
            return true;
        });
        return unique;
    }

    get threadMessages() {
        const msg = this.maildeskStore.selectedMessage;
        if (!msg) return [];

        const threadKey = msg.thread_id || msg.message_id_norm;
        if (!threadKey) return [];

        const all = this.maildeskStore.getThreadMessages?.(threadKey) || [];
        if (!all.length) return [];

        // Build message_id -> DTO map for ancestry lookup
        const byMessageId = new Map();
        for (const m of all) {
            if (m.message_id_norm) {
                byMessageId.set(m.message_id_norm, m);
            }
        }

        // Try ancestry-based filtering first (using headers)
        const hasHeaders = msg.in_reply_to || msg.references_hdr;

        if (hasHeaders) {
            // Build ancestry chain by walking up in_reply_to / references
            const ancestors = [];
            const visited = new Set();

            // Parse references header (space-separated message-ids)
            const parseRefs = (refsStr) => {
                if (!refsStr) return [];
                return refsStr.split(/\s+/).filter(r => r.trim());
            };

            // Get parent message-id from in_reply_to or last reference
            const getParentId = (m) => {
                if (m.in_reply_to) return m.in_reply_to;
                const refs = parseRefs(m.references_hdr);
                return refs.length > 0 ? refs[refs.length - 1] : null;
            };

            // Walk up the ancestry chain
            let parentId = getParentId(msg);
            while (parentId && !visited.has(parentId)) {
                visited.add(parentId);
                const parent = byMessageId.get(parentId);
                if (parent && parent.msg_key !== msg.msg_key) {
                    ancestors.push(parent);
                    parentId = getParentId(parent);
                } else {
                    break;
                }
            }

            if (ancestors.length > 0) {
                // Sort ASC (oldest first, newest at bottom just before selected)
                ancestors.sort((a, b) => (a.sort_ts || 0) - (b.sort_ts || 0));
                return ancestors;
            }
        }

        // FALLBACK: No headers available - use date-based filtering
        // Include only messages BEFORE selected (older)
        const selectedSortTs = msg.sort_ts || 0;
        const selectedDate = msg.date ? new Date(msg.date).getTime() : 0;

        const older = all.filter(m => {
            if (m.msg_key === msg.msg_key) return false;

            const mSortTs = m.sort_ts || 0;
            const mDate = m.date ? new Date(m.date).getTime() : 0;

            if (mSortTs && selectedSortTs) {
                return mSortTs < selectedSortTs;
            }
            return mDate < selectedDate;
        });

        // Sort ASC (oldest first)
        older.sort((a, b) => (a.sort_ts || 0) - (b.sort_ts || 0));
        return older;
    }

    // Iframe Handling

    updateIframeSrcdoc() {
        const msg = this.maildeskStore.selectedMessage;
        // Support both body_original (legacy) and body_html (canonical)
        const body = msg?.body_original || msg?.body_html;
        if (!body) {
            this.state.iframeSrcdoc = "";
            return;
        }
        this.state.iframeSrcdoc = generateIframeSrcdoc(body);
    }

    resizeIframe(height) {
        const iframe = this.iframeRef.el;
        if (iframe && height > 0) {
            // Set height with small buffer for safety
            iframe.style.height = `${height + 2}px`;
        }
    }



    // Action Handlers

    openReplyComposer = (msg) => {
        this.maildeskStore.openComposer?.("reply", msg || this.selectedMessage);
    };

    openReplyAllComposer = (msg) => {
        this.maildeskStore.openComposer?.("replyAll", msg || this.selectedMessage);
    };

    openForwardComposer = (msg) => {
        this.maildeskStore.openComposer?.("forward", msg || this.selectedMessage);
    };

    openDraftComposer = (msg) => {
        this.maildeskStore.openComposer?.("draft", msg || this.selectedMessage);
    };

    deleteSelected = (msg) => {
        this.maildeskStore.deleteMessages?.([msg || this.selectedMessage]);
    };

    moveMessagesToFolder = (folderType, msg) => {
        this.maildeskStore.moveToFolder?.(folderType, [msg || this.selectedMessage]);
    };

    markSelectedAsUnread = () => {
        this.maildeskStore.markAsUnread?.([this.selectedMessage]);
    };

    toggleStarForSelected = () => {
        this.maildeskStore.toggleStar?.([this.selectedMessage]);
    };

    openAssignTagsDialog = (msg) => {
        this.maildeskStore.openTagsDialog?.(msg || this.selectedMessage);
    };

    openMoveToFolderDialog = (msg) => {
        this.maildeskStore.openMoveDialog?.(msg || this.selectedMessage);
    };

    printMessage = () => {
        window.print();
    };

    createPartnerFromMessage = (msg) => {
        this.maildeskStore.createPartnerFromMessage?.(msg || this.selectedMessage);
    };

    createTaskFromMessage = (msg) => {
        this.maildeskStore.createTaskFromMessage?.(msg || this.selectedMessage);
    };

    createTicketFromMessage = (msg) => {
        this.maildeskStore.createTicketFromMessage?.(msg || this.selectedMessage);
    };

    onClickViewProfile = (partnerId) => {
        if (partnerId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                res_id: partnerId,
                views: [[false, "form"]],
                target: "current",
            });
        }
    };

    onClickPartner = (ev, partnerId) => {
        const id = Array.isArray(partnerId) ? partnerId[0] : parseInt(partnerId);
        if (id && !isNaN(id)) {
            this.partnerCard.open(ev.currentTarget, { id: id });
        }
    };

    openLinkedDocument = (msg) => {
        const message = msg || this.selectedMessage;
        if (message?.model && message?.res_id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: message.model,
                res_id: message.res_id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    };

    trustEmailOnce = (msg) => {
        const message = msg || this.selectedMessage;
        if (message) {
            message.force_show_content = true;
            // Trigger reactive update by forcing update
            this.updateIframeSrcdoc();
        }
    };

    trustPartner = (msg) => {
        const message = msg || this.selectedMessage;
        this.maildeskStore.trustPartner?.(message);
        if (message) {
            message.partner_trusted = true;
            message.content_trusted = true;
            this.updateIframeSrcdoc();
        }
    };

    // UI Helpers

    formatUserDate = (dateStr) => {
        if (!dateStr) return "";
        try {
            return new Date(dateStr).toLocaleString(undefined, {
                weekday: "short",
                year: "numeric",
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
            });
        } catch {
            return String(dateStr);
        }
    };
}
