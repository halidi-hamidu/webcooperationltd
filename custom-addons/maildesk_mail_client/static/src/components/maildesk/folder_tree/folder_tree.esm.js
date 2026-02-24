// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Folder Tree.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * FolderTree Component
 *
 * Renders the sidebar with account list, folder tree, and tags.
 */

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/core/popover/popover_hook";
import { PartnerCardPopover } from "../../popovers/partner_card/partner_card_popover.esm.js";

export class FolderTree extends Component {
    static template = "maildesk_mail_client.FolderTreeComponent";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.maildeskStore = useState(useService("maildesk.store"));
        this.partnerCard = usePopover(PartnerCardPopover);
        this.state = useState({
            selectedTagId: [],
        });
    }

    get partnerName() {
        return this.maildeskStore.partnerName;
    }

    get partnerId() {
        return this.maildeskStore.partnerId;
    }

    // Getters

    get accounts() {
        return this.maildeskStore.accountsList || [];
    }

    get tags() {
        return this.maildeskStore.tags || [];
    }

    // Folder tree methods

    getFolderTree = (accountId) => {
        const folders = this.maildeskStore.foldersByAccount;
        if (!folders) return [];
        return folders[accountId] || [];
    };

    getFolderIcon = (folder) => {
        const code = (folder.folder_type || folder.type || "").toLowerCase();

        const map = {
            inbox: "inbox.svg",
            sent: "sent.svg",
            sent_mail: "sent.svg",
            drafts: "drafts.svg",
            draft: "drafts.svg",
            trash: "trash.svg",
            bin: "trash.svg",
            archive: "archive.svg",
            all_mail: "archive.svg",
            spam: "spam.svg",
            junk: "spam.svg",
            starred: "starred.svg",
            flagged: "starred.svg",
            other: "folder.svg",
        };

        const fileName = map[code] || "folder.svg";
        return `/maildesk_mail_client/static/src/icons/${fileName}`;
    };

    getFolderIconSrc = (folder) => {
        return this.getFolderIcon(folder);
    };

    getFolderUnread = (folderId) => {
        // Context Mode: Return snapshot unread counts if available
        if (this.maildeskStore.partnerId || this.maildeskStore.searchQuery) {
            return this.maildeskStore.contextUnreadCounts?.[folderId] || 0;
        }

        // Global Mode: Return live global unread counts
        const folder = this.maildeskStore.folders?.[folderId];
        if (folder && typeof folder.unread_count === "number") {
            return folder.unread_count;
        }
        return this.maildeskStore.unreadCounts?.[folderId] || 0;
    };

    // Folder expand/collapse

    isFolderExpanded = (id, type = 'folder') => {
        return !!this.maildeskStore.expandedFolderIds?.[`${type}_${id}`];
    };

    toggleFolderExpand = (id, type = 'folder') => {
        this.maildeskStore.toggleFolderExpand?.(`${type}_${id}`);
    };

    // Active state checks

    isAllFilterActive = () => {
        return !this.maildeskStore.currentAccountId && !this.maildeskStore.currentFolderId;
    };

    isFolderActive = (folderId) => {
        return this.maildeskStore.currentFolderId === folderId;
    };

    isAccountActive = (accountId) => {
        return this.maildeskStore.currentAccountId === accountId;
    };

    isTagActive = (tagId) => {
        return this.state.selectedTagId.includes(tagId);
    };

    // Event handlers

    onComposeClick = () => {
        this.maildeskStore.openComposer?.("new");
    };

    openComposer = () => {
        this.maildeskStore.openComposer?.("new");
    };

    clearContactFilter = () => {
        this.maildeskStore.clearContactFilter?.();
        this.maildeskStore.setContextUnreadCounts?.(null);
    };

    onResetFilters = () => {
        this.maildeskStore.resetFilters?.();
    };

    resetFilters = () => {
        this.maildeskStore.resetFilters?.();
        this.maildeskStore.setContextUnreadCounts?.(null);
    };

    filterByAccount = (accountId) => {
        this.maildeskStore.filterByAccount?.(accountId);
    };

    filterByFolderAndAccount = (folderId, accountId) => {
        this.maildeskStore.expandFolderParents?.(folderId);
        this.maildeskStore.filterByFolder?.(folderId, accountId);
    };

    onFolderClick = (folderId, accountId) => {
        this.filterByFolderAndAccount(folderId, accountId);
    };

    filterByTag = (tagId) => {
        const idx = this.state.selectedTagId.indexOf(tagId);
        if (idx >= 0) {
            this.state.selectedTagId.splice(idx, 1);
        } else {
            this.state.selectedTagId.push(tagId);
        }
        this.maildeskStore.filterByTags?.(this.state.selectedTagId);
    };

    onTagClick = (tagId) => {
        this.filterByTag(tagId);
    };

    onClearTags = () => {
        this.state.selectedTagId = [];
        this.maildeskStore.filterByTags?.([]);
    };

    // Helpers

    refreshMessages = () => {
        this.maildeskStore.refreshMessages?.();
    };
}
