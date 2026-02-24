// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Mail List.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * MailList Component
 *
 * Renders the message list with search, filters, multi-select actions.
 * Uses maildeskStore for reactive state management.
 */

import { Component, useState, useRef, onMounted, markup } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { debounce } from "@web/core/utils/timing";
import { PartnerCardPopover } from "../../popovers/partner_card/partner_card_popover.esm.js";
import { Toolbar } from "../toolbar/toolbar.esm.js";
import { FilterMenu } from "../filter_menu/filter_menu.esm.js";

export class MailList extends Component {
    static template = "maildesk_mail_client.MailListComponent";
    static components = { Toolbar };
    static props = {
        currentFolderName: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.maildeskStore = useState(useService("maildesk.store"));
        this.actionService = useService("action");
        this.partnerCard = usePopover(PartnerCardPopover);
        this.filterMenu = usePopover(FilterMenu);
        this.listRef = useRef("list");

        // Local reactive state for UI (compatible with v1 template)
        this.state = useState({
            selectedIds: [],           // Array of selected message IDs
            selectedMessage: null,     // Currently viewed message
            hiddenMessageIds: [],      // Messages hidden (e.g., pending delete)
            allSelected: false,        // Select all checkbox state
            isLoading: false,
            focusedIndex: -1,          // Currently focused row for keyboard nav
            lastSelectedIndex: -1,     // Last clicked index for shift-range select
        });

        // Debounced search
        this.debouncedSearch = debounce((query) => {
            this.maildeskStore.setSearchQuery?.(query);
            this.maildeskStore.refreshMessages?.();
        }, 400);

        // Infinite scroll
        onMounted(() => {
            const listEl = this.listRef.el;
            if (listEl) {
                listEl.addEventListener("scroll", () => {
                    const nearBottom = listEl.scrollTop + listEl.clientHeight >= listEl.scrollHeight - 50;
                    if (nearBottom && !this.state.isLoading && this.maildeskStore.hasMore) {
                        this.maildeskStore.loadMoreMessages?.();
                    }
                });
                // Focus the list for keyboard navigation
                listEl.focus();
            }
        });
    }

    // Getters

    get messages() {
        return this.maildeskStore.currentMessages || [];
    }

    get searchQuery() {
        return this.maildeskStore.searchQuery || "";
    }

    get selectedCount() {
        return this.state.selectedIds.length;
    }

    get hasSelection() {
        return this.state.selectedIds.length > 0;
    }

    // Filter methods

    isFilterActive = (filter) => {
        return this.maildeskStore.currentFilter === filter;
    };

    onFilterClick = (filter) => {
        this.maildeskStore.setCurrentFilter?.(filter);
        this.maildeskStore.refreshMessages?.();
    };

    filterBy = (filter) => {
        this.onFilterClick(filter);
    };

    resetFilters = () => {
        this.maildeskStore.resetFilters?.();
    };

    openContactSelector = () => {
        this.maildeskStore.openContactSelector?.();
    };

    onFilterButtonClick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();

        const items = [
            { id: "filter_contact", label: _t("By Contact") },
            { id: "filter_incoming", label: _t("Incoming") },
            { id: "filter_outgoing", label: _t("Outgoing") },
            { id: "filter_unread", label: _t("Only Unread") },
            { id: "filter_starred", label: _t("Only Starred") },
            { id: "reset_filters", label: _t("Reset") },
        ];

        this.filterMenu.open(ev.currentTarget, {
            items,
            onSelect: (act) => {
                switch (act) {
                    case "filter_contact":
                        this.openContactSelector();
                        break;
                    case "filter_incoming":
                        this.filterBy("incoming");
                        break;
                    case "filter_outgoing":
                        this.filterBy("outgoing");
                        break;
                    case "filter_unread":
                        this.filterBy("unread");
                        break;
                    case "filter_starred":
                        this.filterBy("starred");
                        break;
                    case "reset_filters":
                        this.resetFilters(true);
                        break;
                }
            }
        });
    };

    // Search

    onSearchInput = (ev) => {
        const query = ev.target.value;
        this.debouncedSearch(query);
    };

    // Selection methods

    toggleSelection = (indexId) => {
        const msgId = Number(indexId);
        const idx = this.state.selectedIds.indexOf(msgId);
        if (idx >= 0) {
            this.state.selectedIds.splice(idx, 1);
        } else {
            this.state.selectedIds.push(msgId);
        }
        this.state.allSelected = this.state.selectedIds.length === this.messages.length;
    };

    toggleAllSelection = () => {
        if (this.state.selectedIds.length > 0) {
            this.state.selectedIds = [];
            this.state.allSelected = false;
        } else {
            // Store SSOT ids (`maildesk.message_index.id`) for stable, backend-safe actions.
            this.state.selectedIds = this.messages.map((m) => Number(m.id));
            this.state.allSelected = true;
        }
    };

    // Message click handlers

    onMessageClick = (ev, msg) => {
        const messages = this.messages;
        const clickedIndex = messages.findIndex(m => m.msg_key === msg.msg_key);

        // Shift+Click = range selection
        if (ev.shiftKey && this.state.lastSelectedIndex >= 0) {
            this._selectRange(this.state.lastSelectedIndex, clickedIndex);
            return;
        }

        // Ctrl/Cmd+Click = toggle single selection (multi-select)
        if (ev.ctrlKey || ev.metaKey) {
            this.toggleSelection(msg.id);
            this.state.lastSelectedIndex = clickedIndex;
            this.state.focusedIndex = clickedIndex;
            return;
        }

        // Plain click = select message for viewing, clear multi-select
        this.state.selectedIds = [];
        this.state.selectedMessage = msg;
        this.state.lastSelectedIndex = clickedIndex;
        this.state.focusedIndex = clickedIndex;
        this.maildeskStore.selectMessage?.(msg);
    };

    /**
     * Select all messages in range [fromIndex, toIndex] inclusive.
     * Used for Shift+Click range selection.
     */
    _selectRange = (fromIndex, toIndex) => {
        const messages = this.messages;
        const start = Math.min(fromIndex, toIndex);
        const end = Math.max(fromIndex, toIndex);

        const rangeKeys = [];
        for (let i = start; i <= end; i++) {
            if (messages[i]) {
                rangeKeys.push(Number(messages[i].id));
            }
        }

        // Merge with existing selection (Gmail behavior)
        const newSelection = [...new Set([...this.state.selectedIds, ...rangeKeys])];
        this.state.selectedIds = newSelection;
        this.state.allSelected = newSelection.length === messages.length;
        this.state.focusedIndex = toIndex;
    };

    /**
     * Keyboard navigation handler for arrow keys.
     * Arrow keys immediately select and open the message (Gmail behavior).
     */
    onKeyDown = (ev) => {
        const messages = this.messages;
        if (!messages.length) return;

        const key = ev.key;
        let handled = false;

        if (key === "ArrowDown") {
            ev.preventDefault();
            handled = true;
            const newIndex = Math.min(this.state.focusedIndex + 1, messages.length - 1);
            this.state.focusedIndex = newIndex;
            this.state.lastSelectedIndex = newIndex;

            // If shift is held, extend selection instead of opening
            if (ev.shiftKey && this.state.lastSelectedIndex >= 0) {
                this._selectRange(this.state.lastSelectedIndex, newIndex);
            } else {
                // Immediately select and open the message
                const msg = messages[newIndex];
                if (msg) {
                    this.state.selectedIds = [];
                    this.state.selectedMessage = msg;
                    this.maildeskStore.selectMessage?.(msg);
                }
            }

            this._scrollToFocused();
        } else if (key === "ArrowUp") {
            ev.preventDefault();
            handled = true;
            const newIndex = Math.max(this.state.focusedIndex - 1, 0);
            this.state.focusedIndex = newIndex;
            this.state.lastSelectedIndex = newIndex;

            // If shift is held, extend selection instead of opening
            if (ev.shiftKey && this.state.lastSelectedIndex >= 0) {
                this._selectRange(this.state.lastSelectedIndex, newIndex);
            } else {
                // Immediately select and open the message
                const msg = messages[newIndex];
                if (msg) {
                    this.state.selectedIds = [];
                    this.state.selectedMessage = msg;
                    this.maildeskStore.selectMessage?.(msg);
                }
            }

            this._scrollToFocused();
        } else if (key === "Enter" || key === " ") {
            ev.preventDefault();
            handled = true;
            const msg = messages[this.state.focusedIndex];
            if (msg) {
                this.state.selectedMessage = msg;
                this.maildeskStore.selectMessage?.(msg);
            }
        } else if (key === "Escape") {
            // Clear selection
            this.state.selectedIds = [];
            this.state.allSelected = false;
        }

        // Stop propagation if we handled the key
        if (handled) {
            ev.stopPropagation();
        }
    };

    /**
     * Scroll the focused message into view.
     */
    _scrollToFocused = () => {
        const listEl = this.listRef.el;
        if (!listEl) return;

        const focusedRow = listEl.querySelector(`[data-message-index="${this.state.focusedIndex}"]`);
        if (focusedRow) {
            focusedRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
    };

    onMessageRightClick = (ev, msg) => {
        ev.preventDefault();
        ev.stopPropagation();
        this._openContextMenu(ev, msg);
    };

    /**
     * Open context menu for message actions.
     * Uses popover pattern but with custom items/logic as requested.
     */
    _openContextMenu = (ev, msg) => {
        // User-requested menu structure
        const items = [
            { id: "reply", label: _t("Reply"), show: true },
            { id: "reply_all", label: _t("Reply All"), show: true },
            { id: "forward", label: _t("Forward"), show: true },
            { id: "mark_read", label: _t("Mark as Read"), show: !msg.is_read },
            { id: "mark_unread", label: _t("Mark as Unread"), show: msg.is_read },
            {
                id: "star",
                label: msg.is_starred ? _t("Remove Star") : _t("Add Star"),
                show: true,
            },
            { id: "move", label: _t("Move to Folder…"), show: true },
            {
                id: "tag",
                label: _t("Assign Tags…"),
                show: Boolean(this.maildeskStore.tags?.length),
            },
            {
                id: "contact",
                label: _t("Create Contact"),
                show: !msg.avatar_partner_id,
            },
            {
                id: "open_contact",
                label: _t("Open Contact"),
                show: Boolean(msg.avatar_partner_id),
            },
            {
                id: "open_doc",
                label: _t("Open Linked Document"),
                show: Boolean(msg.model && msg.res_id),
            },
            { id: "print", label: _t("Print"), show: true },
            { id: "delete", label: _t("Delete"), show: true },
        ];

        // Filter visible items
        const visibleItems = items.filter(item => item.show);

        // VIEWPORT-AWARE POSITIONING
        // Opens menu above cursor when near bottom of viewport
        const viewportHeight = window.innerHeight;
        const clickY = ev.clientY;
        const isNearBottom = clickY > viewportHeight * 0.6;
        const position = isNearBottom ? "top" : "bottom";

        this.filterMenu.open(ev.target, {
            items: visibleItems,
            onSelect: (action) => this._handleContextAction(action, msg),
        }, { position });
    };

    /**
     * Handle context menu action selection.
     */
    _handleContextAction = (action, msg) => {
        const messages = this.state.selectedIds.length > 1
            ? this.messages.filter((m) => this.state.selectedIds.includes(Number(m.id)))
            : [msg];

        switch (action) {
            case "reply":
                this.maildeskStore.openComposer?.("reply", msg);
                break;
            case "reply_all":
                this.maildeskStore.openComposer?.("replyAll", msg);
                break;
            case "forward":
                this.maildeskStore.openComposer?.("forward", msg);
                break;
            case "mark_read":
                this.maildeskStore.markAsRead?.(messages);
                break;
            case "mark_unread":
                this.maildeskStore.markAsUnread?.(messages);
                break;
            case "star":
                this.maildeskStore.toggleStar?.(messages);
                break;
            case "archive":
                this.maildeskStore.archiveMessages?.(messages);
                break;
            case "delete":
                this.maildeskStore.deleteMessages?.(messages);
                this.state.selectedIds = [];
                break;
            case "move":
                this.maildeskStore.openMoveDialog?.(messages);
                break;
            case "tag":
                this.maildeskStore.openTagsDialog?.(msg);
                break;
            case "contact":
                this.maildeskStore.createPartnerFromMessage?.(msg);
                break;
            case "open_contact":
                if (msg.avatar_partner_id) {
                    this.partnerCard.open(document.body, { id: parseInt(msg.avatar_partner_id, 10) });
                }
                break;
            case "open_doc":
                if (msg.model && msg.res_id) {
                    this.actionService.doAction({
                        type: "ir.actions.act_window",
                        res_model: msg.model,
                        res_id: msg.res_id,
                        views: [[false, "form"]],
                        target: "current",
                    });
                }
                break;
            case "print":
                // TODO: Implementation for print
                window.print();
                break;
        }
    };

    onClickPartner = (ev, partnerId) => {
        if (partnerId) {
            this.partnerCard.open(ev.currentTarget, { id: parseInt(partnerId, 10) });
        }
    };

    // Quick actions (hover buttons)

    openReplyComposer = (msg) => {
        this.maildeskStore.openComposer?.("reply", msg);
    };

    openForwardComposer = (msg) => {
        this.maildeskStore.openComposer?.("forward", msg);
    };

    // Bulk actions

    _getSelectedMessages = () => {
        return this.messages.filter((m) => this.state.selectedIds.includes(Number(m.id)));
    };

    archiveSelected = () => {
        const msgs = this._getSelectedMessages();
        if (!msgs.length) return;
        this.maildeskStore.archiveMessages?.(msgs);
        this.state.selectedIds = [];
    };

    deleteSelected = (msg) => {
        // Handle both single message (arg) and bulk selection
        let msgs = [];
        if (msg && msg.id) {
            msgs = [msg];
        } else {
            msgs = this._getSelectedMessages();
        }

        if (!msgs.length) return;
        this.maildeskStore.deleteMessages?.(msgs);
        this.state.selectedIds = [];
    };

    markSelectedAsRead = () => {
        const msgs = this._getSelectedMessages();
        if (!msgs.length) return;
        this.maildeskStore.markAsRead?.(msgs);
    };

    markSelectedAsUnread = () => {
        const msgs = this._getSelectedMessages();
        if (!msgs.length) return;
        this.maildeskStore.markAsUnread?.(msgs);
    };

    toggleStarForSelected = () => {
        const msgs = this._getSelectedMessages();
        if (!msgs.length) return;
        this.maildeskStore.toggleStar?.(msgs);
    };

    openMoveToFolderDialog = () => {
        const msgs = this._getSelectedMessages();
        if (!msgs.length) return;
        this.maildeskStore.openMoveDialog?.(msgs);
    };
}
