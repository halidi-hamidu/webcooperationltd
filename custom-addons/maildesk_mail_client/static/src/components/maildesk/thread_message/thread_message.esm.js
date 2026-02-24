// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Thread Message.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * ThreadMessage Component
 *
 * Renders a SINGLE message within a thread conversation.
 * Compact icon-only toolbar. Body ALWAYS visible (no lazy loading).
 */

import { Component, useState, useRef, onMounted, onWillUnmount, onWillRender } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { AttachmentList } from "@mail/core/common/attachment_list";
import { generateIframeSrcdoc, getIframeSandbox } from "../../../utils/maildesk_iframe.esm.js";
import { PartnerCardPopover } from "../../popovers/partner_card/partner_card_popover.esm.js";

export class ThreadMessage extends Component {
    static template = "maildesk_mail_client.ThreadMessageComponent";
    static components = { AttachmentList };
    static props = {
        message: Object,
    };

    setup() {
        this.action = useService("action");
        this.maildeskStore = useService("maildesk.store");
        this.partnerCard = usePopover(PartnerCardPopover);
        this.iframeRef = useRef("iframe");

        this.state = useState({
            iframeSrcdoc: "",
            lastBodyOriginal: null,
        });

        // Handle postMessage from iframe
        // Handle postMessage from iframe
        this.messageHandler = (ev) => {
            // SOURCE VALIDATION: Only accept messages from the current active iframe
            if (!this.iframeRef.el || ev.source !== this.iframeRef.el.contentWindow) {
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

        onWillRender(() => {
            const body = this.props.message?.body_html;
            if (body !== this.state.lastBodyOriginal) {
                this.state.lastBodyOriginal = body;
                Promise.resolve().then(() => this.updateIframeSrcdoc());
            }
        });
    }





    get message() {
        return this.props.message;
    }

    get iframeSandbox() {
        const msg = this.props.message;
        return getIframeSandbox(msg?.force_show_content || msg?.content_trusted);
    }

    get folderName() {
        const folderId = this.message.folder_id;
        if (!folderId) return "";
        const folder = this.maildeskStore.folders?.[folderId];
        return folder ? folder.name : "";
    }

    get mailboxName() {
        let accountId = this.message.account_id;
        if (Array.isArray(accountId)) accountId = accountId[0];
        if (!accountId) return "";
        const account = this.maildeskStore.accounts?.[accountId];
        return account ? (account.sender_name || account.name || "") : "";
    }

    get isSentFolder() {
        return this.props.message?.folder_type === "sent";
    }

    get mailboxEmail() {
        let accountId = this.props.message?.account_id;
        if (Array.isArray(accountId)) accountId = accountId[0];
        if (!accountId) return "";
        const account = this.maildeskStore.accounts?.[accountId];
        return account?.email || "";
    }

    get attachmentsForAttachmentList() {
        const atts = this.message?.attachments || [];
        // Deduplicate by id to prevent Owl "duplicate key" errors
        const seen = new Set();
        const unique = atts.filter(a => {
            if (!a?.id || seen.has(a.id)) return false;
            seen.add(a.id);
            return true;
        });
        return unique;
    }


    // IFRAME HANDLING


    updateIframeSrcdoc() {
        const msg = this.props.message;
        if (!msg?.body_html) {
            this.state.iframeSrcdoc = "";
            return;
        }
        this.state.iframeSrcdoc = generateIframeSrcdoc(msg.body_html);
    }

    resizeIframe(height) {
        const iframe = this.iframeRef.el;
        if (iframe && height > 0) {
            iframe.style.height = `${height + 2}px`;
        }
    }







    openReplyComposer = (msg) => {
        this.maildeskStore.openComposer?.("reply", msg);
    };

    openReplyAllComposer = (msg) => {
        this.maildeskStore.openComposer?.("replyAll", msg);
    };

    openForwardComposer = (msg) => {
        this.maildeskStore.openComposer?.("forward", msg);
    };

    deleteSelected = (msg) => {
        this.maildeskStore.deleteMessages?.([msg]);
    };

    archiveMessage = (msg) => {
        this.maildeskStore.archiveMessages?.([msg]);
    };

    toggleStar = (msg) => {
        this.maildeskStore.toggleStar?.([msg]);
    };

    onClickPartner = (ev, partnerId) => {
        const id = Array.isArray(partnerId) ? partnerId[0] : parseInt(partnerId);
        if (id && !isNaN(id)) {
            this.partnerCard.open(ev.currentTarget, { id: id });
        }
    };

    trustEmailOnce = (msg) => {
        if (msg) {
            msg.force_show_content = true;
            this.updateIframeSrcdoc();
        }
    };

    trustPartner = (msg) => {
        this.maildeskStore.trustPartner?.(msg);
        if (msg) {
            msg.partner_trusted = true;
            msg.content_trusted = true;
            this.updateIframeSrcdoc();
        }
    };


    // UI HELPERS


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
