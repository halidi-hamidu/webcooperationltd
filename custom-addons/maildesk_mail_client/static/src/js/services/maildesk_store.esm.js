// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk MailDesk Store.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { registry } from "@web/core/registry";
import { reactive } from "@odoo/owl";
import { FileModel } from "@web/core/file_viewer/file_model";

/**
 * MailDesk Store Service
 *
 * Data store for MailDesk state. Matches Odoo mail.store.service pattern.
 * All collections use plain Objects or Arrays for OWL reactivity.
 */

class MailDeskStore {
    constructor() {
        // Data Collections

        /** @type {Object<string, Object>} msg_key → Message */
        this.messages = {};

        /** @type {Object<string, Object[]>} thread_id → Message[] (sorted) */
        this.threadMessages = {};

        /** @type {Object<number, Object>} folder.id → Folder */
        this.folders = {};

        /** @type {Object<number, Object>} account.id → Account */
        this.accounts = {};

        /** @type {number[]} Ordered list of account IDs from backend */
        this.accountsOrder = [];

        /** @type {Object<number, Object[]>} account.id → Folder[] (tree structure) */
        this.foldersByAccount = {};

        /** @type {Object[]} Array of tag objects */
        this.tags = [];

        // Selection State

        /** @type {string|null} Currently selected message key */
        this.selectedMsgKey = null;

        /** @type {string[]} Multi-select mode keys (Array, not Set) */
        this.selectedMsgKeys = [];

        /** @type {number|null} Current account ID */
        this.currentAccountId = null;

        /** @type {number|null} Current folder ID */
        this.currentFolderId = null;

        /** @type {string} Current filter (all, starred, unread) */
        this.currentFilter = "all";

        /** @type {string} Current search query */
        this.searchQuery = "";

        /** @type {number[]} Selected tag IDs for filtering */
        this.selectedTagIds = [];

        // Loading states for progressive rendering
        // Using Objects (not Set) for immutable replacement patterns.
        this.loading = {
            accounts: true,      // Initial load
            folders: {},         // Object: { [accountId]: true } - immutable updates
            messages: false,     // Message list loading
            messageBody: false,  // Full message body loading (iframe)
        };

        /** @type {number|null} Partner ID for contact filtering */
        this.partnerId = null;
        this.partnerName = "";

        /** @type {Object} folder.id → unread count */
        this.unreadCounts = {};

        /** @type {Object|null} Context-aware unread counts (when filter active) */
        this.contextUnreadCounts = null;

        /** @type {Object<string, boolean>} Expanded folder/account IDs (Object, not Set) */
        this.expandedFolderIds = {};

        /** @type {Object<number, boolean>} Hidden message IDs (Object, not Set) */
        this.hiddenMsgIds = {};

        /** @type {string} Key representing the current list query context */
        this.listContextKey = this._buildListContextKey();

        /** @type {string[]} Ordered msg_key values for the current list results */
        this.listMsgKeys = [];

        /** @type {number|null} Total number of messages matching current list query */
        this.listTotalCount = null;

        /** @type {boolean} Has more messages for pagination */
        this.hasMore = true;
    }

    // Message Operations

    /**
     * Insert or update a message by msg_key.
     * Uses Object spread for immutable updates.
     * @param {string} msgKey - Composite key (account|folder|uid)
     * @param {Object} data - Message data to merge
     * @returns {Object} The updated message
     */
    upsertMessage(msgKey, data) {
        data = this._normalizeMessageForOdoo(data);
        const existing = this.messages[msgKey];
        if (existing) {
            // Merge into existing object (mutate in place - OK since OWL tracks object identity)
            Object.assign(existing, data);
            return existing;
        }
        const message = { ...data, msg_key: msgKey };
        // Immutable object replacement
        this.messages = { ...this.messages, [msgKey]: message };
        return message;
    }

    /**
     * Update message details SAFE mode (protects list fields).
     * @param {string} msgKey
     * @param {Object} details - Full details payload
     */
    updateMessageDetails(msgKey, details) {
        details = this._normalizeMessageForOdoo(details);
        const existing = this.messages[msgKey];
        if (!existing) {
            return this.upsertMessage(msgKey, details);
        }

        // List of protected fields that should NOT be overwritten if empty in details
        const protectedFields = [
            'preview_text',
            'sender_display_name',
            'avatar_html',
            'is_read',
            'is_starred',
            'subject',
            'date',
            'formatted_date',
            'folder_type',
            'visual_email',
            'tag_ids',
            'tags'
        ];

        const safeUpdate = { ...details };

        // Clean protected fields from update if they are empty/falsy in details
        for (const field of protectedFields) {
            if (!details[field] && existing[field]) {
                delete safeUpdate[field];
            }
        }

        safeUpdate.msg_key = msgKey;
        Object.assign(existing, safeUpdate);
        return existing;
    }

    /**
     * Insert multiple messages.
     * @param {Object[]} messages - Array of message objects
     * @param {boolean} replace - If true, clear existing messages before inserting (for search/filter)
     * @returns {Object[]} Array of inserted/updated messages
     */
    insertMessages(messages, replace = false) {
        const result = [];

        // CRITICAL: If replace=true, start with empty object (for search/filter results)
        // Otherwise merge with existing messages (for pagination)
        const newMessages = replace ? {} : { ...this.messages };

        for (const msg of messages) {
            const normalizedMsg = this._normalizeMessageForOdoo(msg);
            const key = msg.msg_key || this._buildMsgKey(msg);
            if (newMessages[key]) {
                Object.assign(newMessages[key], normalizedMsg);
                result.push(newMessages[key]);
            } else {
                const newMsg = { ...normalizedMsg, msg_key: key };
                newMessages[key] = newMsg;
                result.push(newMsg);
            }
        }
        this.messages = newMessages;

        return result;
    }

    /**
     * Get a message by key.
     * @param {string} msgKey
     * @returns {Object|undefined}
     */
    getMessage(msgKey) {
        return this.messages[msgKey];
    }

    /**
     * Delete a message by key.
     * Uses immutable object patterns.
     * @param {string} msgKey
     */
    deleteMessage(msgKey) {
        const { [msgKey]: _, ...remaining } = this.messages;
        this.messages = remaining;
        // Also clean from selection
        this.selectedMsgKeys = this.selectedMsgKeys.filter(k => k !== msgKey);
        if (this.selectedMsgKey === msgKey) {
            this.selectedMsgKey = null;
        }
    }

    /**
     * Get messages for display, sorted by date descending.
     * @returns {Object[]} All messages in store, sorted by date descending
     */
    get currentMessages() {
        const contextKey = this._buildListContextKey();
        const keys = this.listContextKey === contextKey ? (this.listMsgKeys || []) : [];

        const result = [];
        for (const msgKey of keys) {
            const msg = this.messages[msgKey];
            if (!msg) continue;
            if (this.hiddenMsgIds[msg.id]) continue;
            result.push(msg);
        }
        // Sort by immutable sort_ts (UNIX timestamp) for stable ordering
        // NEVER use new Date(date) - that causes position jumps on click/open
        result.sort((a, b) => {
            const byTs = (b.sort_ts || 0) - (a.sort_ts || 0);
            if (byTs) return byTs;
            return (b.id || 0) - (a.id || 0);
        });
        return result;
    }

    // Thread Operations

    /**
     * Set messages for a specific thread.
     * @param {string} threadId
     * @param {Object[]} messages
     */
    setThreadMessages(threadId, messages) {
        const normalized = (messages || []).map((m) => this._normalizeMessageForOdoo(m));
        this.threadMessages = { ...this.threadMessages, [threadId]: normalized };
    }

    /**
     * Get messages for thread.
     * @param {string} threadId
     * @returns {Object[]|undefined}
     */
    getThreadMessages(threadId) {
        return this.threadMessages[threadId];
    }

    // Account Operations

    /**
     * Set accounts list.
     * Uses Object for accounts.
     * @param {Object[]} accounts
     */
    setAccounts(accounts) {
        const newAccounts = {};
        const newOrder = [];
        for (const acc of accounts) {
            newAccounts[acc.id] = acc;
            newOrder.push(acc.id);
            if (acc.folders) {
                this.setFoldersForAccount(acc.id, acc.folders);
            }
        }
        this.accounts = newAccounts;
        this.accountsOrder = newOrder;
    }

    /**
     * Get account by ID.
     * @param {number} accountId
     * @returns {Object|undefined}
     */
    getAccount(accountId) {
        return this.accounts[accountId];
    }

    /**
     * Get all accounts as array.
     * @returns {Object[]}
     */
    get accountsList() {
        return this.accountsOrder.map(id => this.accounts[id]).filter(Boolean);
    }

    // Folder Operations

    /**
     * Set folder tree for an account.
     * Uses Object for foldersByAccount and folders.
     * @param {number} accountId
     * @param {Object[]} folders
     */
    setFoldersForAccount(accountId, folders) {
        this.foldersByAccount = { ...this.foldersByAccount, [accountId]: folders };

        // Index individual folders
        const newFolders = { ...this.folders };
        const indexFolders = (list, parentId = null) => {
            for (const f of list) {
                if (!f.parent_id && parentId) f.parent_id = parentId;
                if (!f.account_id && accountId) f.account_id = accountId;
                newFolders[f.id] = f;
                if (f.children?.length) {
                    indexFolders(f.children, f.id);
                }
            }
        };
        indexFolders(folders);
        this.folders = newFolders;
    }

    /**
     * Get folder by ID.
     * @param {number} folderId
     * @returns {Object|undefined}
     */
    getFolder(folderId) {
        return this.folders[folderId];
    }

    /**
     * Get folder tree for account.
     * @param {number} accountId
     * @returns {Object[]}
     */
    getFoldersForAccount(accountId) {
        return this.foldersByAccount[accountId] || [];
    }

    /**
     * Find folder by type (inbox, archive, trash, etc.) for account.
     * @param {number} accountId
     * @param {string} folderType
     * @returns {Object|undefined}
     */
    findFolderByType(accountId, folderType) {
        const folders = this.getFoldersForAccount(accountId);
        const searchInTree = (list) => {
            for (const f of list) {
                if (f.folder_type === folderType) {
                    return f;
                }
                if (f.children?.length) {
                    const found = searchInTree(f.children);
                    if (found) return found;
                }
            }
            return null;
        };
        return searchInTree(folders);
    }

    /**
     * Update unread count for a folder.
     * @param {number} folderId
     * @param {number} unreadCount
     */
    setFolderUnreadCount(folderId, unreadCount) {
        const folder = this.folders[folderId];
        if (folder) {
            folder.unread_count = unreadCount;
        }
    }

    /**
     * Get unread count for folder.
     * @param {number} folderId
     * @returns {number}
     */
    getFolderUnreadCount(folderId) {
        return this.folders[folderId]?.unread_count || 0;
    }

    /**
     * Find folder ID by IMAP name or name within an account.
     * @param {number} accountId
     * @param {string} folderName
     * @returns {number|null}
     */
    findFolderId(accountId, folderName) {
        const folders = this.getFoldersForAccount(accountId);
        if (!folders) return null;

        const find = (list) => {
            for (const f of list) {
                // Match by imap_name (preferred) or name
                if ((f.imap_name === folderName) || (f.name === folderName)) {
                    return f.id;
                }
                if (f.children?.length) {
                    const found = find(f.children);
                    if (found) return found;
                }
            }
            return null;
        };

        return find(folders);
    }

    // Selection state updates

    /**
     * Set selected message key.
     * @param {string|null} msgKey
     */
    setSelectedMsgKey(msgKey) {
        this.selectedMsgKey = msgKey;
    }

    /**
     * Get the currently selected message object.
     * @returns {Object|null}
     */
    get selectedMessage() {
        if (!this.selectedMsgKey) return null;
        return this.messages[this.selectedMsgKey] || null;
    }

    /**
     * Toggle message selection (multi-select mode).
     * Uses immutable array patterns.
     * @param {string} msgKey
     */
    toggleMessageSelection(msgKey) {
        if (this.selectedMsgKeys.includes(msgKey)) {
            this.selectedMsgKeys = this.selectedMsgKeys.filter(k => k !== msgKey);
        } else {
            this.selectedMsgKeys = [...this.selectedMsgKeys, msgKey];
        }
    }

    /**
     * Clear multi-select.
     */
    clearSelection() {
        this.selectedMsgKeys = [];
    }

    /**
     * Set current account and folder.
     * @param {number|null} accountId
     * @param {number|null} folderId
     */
    setCurrentLocation(accountId, folderId) {
        this.currentAccountId = accountId;
        this.currentFolderId = folderId;
        this.resetListResults();
    }

    /**
     * Set current filter.
     * @param {string} filter
     */
    setCurrentFilter(filter) {
        this.currentFilter = filter;
        this.resetListResults();
    }

    /**
     * Set search query.
     * @param {string} query
     */
    setSearchQuery(query) {
        this.searchQuery = query;
        this.resetListResults();
    }

    /**
     * Set selected tag IDs.
     * @param {number[]} tagIds
     */
    setSelectedTagIds(tagIds) {
        this.selectedTagIds = tagIds || [];
        this.resetListResults();
    }

    /**
     * Set partner ID for filtering.
     * @param {number|null} partnerId
     */
    setPartnerId(partnerId) {
        this.partnerId = partnerId;
        this.resetListResults();
    }

    /**
     * Set tags list.
     * @param {Object[]} tags
     */
    setTags(tags) {
        this.tags = tags || [];
    }

    /**
     * Set folders for account (alias for setFoldersForAccount).
     * @param {number} accountId
     * @param {Object[]} folders
     */
    setFolders(accountId, folders) {
        this.setFoldersForAccount(accountId, folders);
    }

    /**
     * Update message flags (is_read, is_starred, etc).
     * @param {string} msgKey
     * @param {Object} flags
     */
    updateMessageFlags(msgKey, flags) {
        const msg = this.messages[msgKey];
        if (msg) {
            Object.assign(msg, flags);
        }
    }

    setUnreadCount(folderId, count) {
        this.unreadCounts = { ...this.unreadCounts, [folderId]: count };
    }

    setContextUnreadCounts(counts) {
        this.contextUnreadCounts = counts;
    }

    /**
     * Expand folder parents (recurses up to root).
     * Uses immutable object patterns.
     * @param {number} folderId
     */
    expandFolderParents(folderId) {
        if (!folderId) return;
        const folder = this.folders[folderId];
        if (!folder) return;

        const newExpanded = { ...this.expandedFolderIds };

        // If folder belongs to an account, expand the account
        if (folder.account_id) {
            const accId = Array.isArray(folder.account_id) ? folder.account_id[0] : folder.account_id;
            if (accId) newExpanded[`account_${accId}`] = true;
        }

        let current = folder;
        while (current && current.parent_id) {
            const pid = Array.isArray(current.parent_id) ? current.parent_id[0] : current.parent_id;
            if (pid) {
                newExpanded[`folder_${pid}`] = true;
                current = this.folders[pid];
            } else {
                break;
            }
        }
        this.expandedFolderIds = newExpanded;
    }

    /**
     * Toggle folder expansion.
     * Uses immutable object patterns.
     * @param {number|string} id
     */
    toggleFolderExpand(id) {
        if (this.expandedFolderIds[id]) {
            const { [id]: _, ...remaining } = this.expandedFolderIds;
            this.expandedFolderIds = remaining;
        } else {
            this.expandedFolderIds = { ...this.expandedFolderIds, [id]: true };
        }
    }

    /**
     * Expand a specific ID.
     * @param {number|string} id
     */
    expandFolder(id) {
        this.expandedFolderIds = { ...this.expandedFolderIds, [id]: true };
    }

    // Helpers

    _normalizeMessageForOdoo(msg) {
        if (!msg || typeof msg !== "object") {
            return msg;
        }
        if (!("attachments" in msg)) {
            return msg;
        }
        const attachments = this._normalizeAttachmentsForOdoo(msg.attachments);
        // Preserve object identity if we can (OWL reactive usage), but avoid
        // mutating frozen/immutable payloads.
        try {
            msg.attachments = attachments;
            return msg;
        } catch {
            return { ...msg, attachments };
        }
    }

    _normalizeAttachmentsForOdoo(attachments) {
        if (!Array.isArray(attachments)) {
            return [];
        }
        return attachments
            .filter((a) => !!a)
            .map((a) => this._normalizeAttachmentForOdoo(a));
    }

    _normalizeAttachmentForOdoo(raw) {
        try {
            if (
                typeof window !== "undefined" &&
                window.localStorage?.getItem("maildesk_disable_filemodel") === "1"
            ) {
                return raw;
            }
        } catch {
            // ignore
        }
        // Odoo AttachmentList/FileViewer expects a FileModel-like object with getters:
        // - urlRoute/urlQueryParams/defaultSource/downloadUrl (see `odoo/addons/web/static/src/core/file_viewer/file_model.js`)
        // In MailDesk we keep attachments as plain JSON, so we wrap them into FileModel.
        if (!raw || typeof raw !== "object") {
            return raw;
        }
        if (raw instanceof FileModel) {
            return raw;
        }

        let data;
        try {
            data = { ...raw };
        } catch (e) {
            console.warn("[MailDesk] Failed to clone attachment payload", e);
            return raw;
        }

        // Normalize common fields used by FileModel.
        if (!data.name && data.filename) {
            data.name = data.filename;
        }
        if (!data.filename && data.name) {
            data.filename = data.name;
        }
        if (typeof data.id === "string" && /^\d+$/.test(data.id)) {
            data.id = parseInt(data.id, 10);
        }

        // Keep URL/link attachments as plain objects (AttachmentList supports `type === "url"` directly).
        if (data.type === "external") {
            data.type = "url";
        }
        if (data.type === "url") {
            data.url = data.url || data.download_url || data.preview_url || "";
            // Ensure FileViewer won't open this on card click.
            data.isViewable = false;
            data.isImage = false;
            return data;
        }

        // Strip keys that would collide with FileModelMixin getters.
        // Otherwise `Object.assign(new FileModel(), data)` throws in strict mode.
        const forbiddenKeys = [
            // URL pipeline getters
            "urlRoute",
            "urlQueryParams",
            "defaultSource",
            "downloadUrl",
            "displayName",
            // Type getters
            "isImage",
            "isPdf",
            "isText",
            "isVideo",
            "isViewable",
            "isUrl",
            "isUrlYoutube",
            // MailDesk legacy aliases
            "previewUrl",
            "preview_url",
            "download_url",
        ];
        for (const k of forbiddenKeys) {
            if (k in data) {
                delete data[k];
            }
        }

        // Wrap into FileModel instance - set properties individually to preserve getter chain
        try {
            const fm = new FileModel();
            for (const key of Object.keys(data)) {
                fm[key] = data[key];
            }
            return fm;
        } catch (e) {
            console.warn("[MailDesk] Failed to wrap attachment into FileModel", e);
            return raw;
        }
    }

    /**
     * Build a stable key for the current list query context.
     * @returns {string}
     */
    _buildListContextKey() {
        const accountId = this.currentAccountId;
        const folderId = this.currentFolderId;
        const locationKey = folderId != null ? `fld=${folderId}` : `acc=${accountId ?? ""}`;
        const filter = this.currentFilter ?? "";
        const search = this.searchQuery ?? "";
        const partnerId = this.partnerId ?? "";
        const tagIds = Array.isArray(this.selectedTagIds)
            ? [...this.selectedTagIds].sort((a, b) => a - b)
            : [];
        return `loc=${locationKey};filter=${filter};search=${search};partner=${partnerId};tags=${tagIds.join(",")}`;
    }

    resetListResults() {
        this.listContextKey = this._buildListContextKey();
        this.listMsgKeys = [];
        this.listTotalCount = null;
    }

    setListResults(msgKeys, contextKey) {
        this.listContextKey = contextKey;
        this.listMsgKeys = Array.isArray(msgKeys) ? [...msgKeys] : [];
    }

    setListTotalCount(totalCount, contextKey) {
        if (this.listContextKey !== contextKey) return;
        const n = Number(totalCount);
        this.listTotalCount = Number.isFinite(n) ? n : null;
    }

    appendListResults(msgKeys, contextKey) {
        if (!Array.isArray(msgKeys) || !msgKeys.length) return;
        if (this.listContextKey !== contextKey) {
            this.setListResults(msgKeys, contextKey);
            return;
        }
        const existing = new Set(this.listMsgKeys);
        const toAppend = [];
        for (const k of msgKeys) {
            if (!existing.has(k)) toAppend.push(k);
        }
        if (toAppend.length) {
            this.listMsgKeys = [...this.listMsgKeys, ...toAppend];
        }
    }

    /**
     * Build msg_key from message object.
     * @param {Object} msg
     * @returns {string}
     */
    _buildMsgKey(msg) {
        const acc = Array.isArray(msg.account_id) ? msg.account_id[0] : msg.account_id;
        const fld = msg.folder_id;
        const uid = msg.uid ?? msg.id;
        return `${acc}|${fld}|${uid}`;
    }

    /**
     * Clear all messages (for full refresh).
     */
    clearMessages() {
        this.messages = {};
        this.selectedMsgKey = null;
        this.selectedMsgKeys = [];
        this.hiddenMsgIds = {};
    }

    /**
     * Hide messages (optimistic delete).
     * Uses immutable object patterns.
     * @param {number[]} ids
     */
    hideMessages(ids) {
        const newHidden = { ...this.hiddenMsgIds };
        for (const id of ids) newHidden[id] = true;
        this.hiddenMsgIds = newHidden;
    }

    /**
     * Unhide messages (undo delete).
     * @param {number[]} ids
     */
    unhideMessages(ids) {
        const newHidden = { ...this.hiddenMsgIds };
        for (const id of ids) delete newHidden[id];
        this.hiddenMsgIds = newHidden;
    }
}

// Service registration

export const maildeskStoreService = {
    dependencies: [],
    /**
     * Return a reactive store instance so all services/components share the same
     * reactive reference (bus updates must trigger UI re-render).
     *
     * @param {import("@web/env").OdooEnv} env
     * @returns {MailDeskStore}
     */
    start(env) {
        return reactive(new MailDeskStore());
    },
};

registry.category("services").add("maildesk.store", maildeskStoreService);
