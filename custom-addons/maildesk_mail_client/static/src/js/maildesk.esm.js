// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk MailDesk.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import {
  Component,
  markup,
  onMounted,
  onWillStart,
  onWillUnmount,
  useState,
} from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

// Dialogs
import { AssignTagsDialog } from "../components/dialogs/assign_tags/assign_tags_dialog.esm.js";
import { ContactPickerDialog } from "../components/dialogs/contact_picker/contact_picker_dialog.esm.js";
import { MoveToFolderDialog } from "../components/dialogs/move_to_folder/move_to_folder_dialog.esm.js";
import { UndoToast } from "../components/maildesk/undo_toast/undo_toast.esm.js";

// Child components
import { FolderTree } from "../components/maildesk/folder_tree/folder_tree.esm.js";
import { MailList } from "../components/maildesk/mail_list/mail_list.esm.js";
import { MailDetail } from "../components/maildesk/mail_detail/mail_detail.esm.js";

// Utilities
import { normalizeMessage } from "../utils/maildesk_dom.esm.js";

export class MailDesk extends Component {
  static template = "maildesk_mail_client.MailDesk";
  static components = { FolderTree, MailList, MailDetail, UndoToast };
  static props = {
    action: Object,
    actionId: Number,
    updateActionState: Function,
    className: { type: String, optional: true },
    ...standardActionServiceProps,
  };

  // Setup

  setup() {
    this.rpc = rpc;
    this.orm = useService("orm");
    this.dialog = useService("dialog");
    this.notification = useService("notification");
    this.action = useService("action");
    this.maildeskStore = useState(useService("maildesk.store"));
    // Pattern mirrored from Odoo Mail: use global composer service
    this.composerService = useService("maildesk.composer");

    // Bus-driven sync service
    this.syncService = useService("maildesk.sync");

    this.state = useState({
      preselectMessageId: null,
      messageOffset: 0,
      messageLimit: 30,
      loadingMore: false,
      undoToast: null,
      hasMore: true, // Phase 4B: Track pagination state
    });

    this._reqStamp = 0;

    onWillStart(() => {
      // Synchronous wiring only.
    });

    // Fire data loading immediately (non-blocking)
    this.loadInitialMessages();

    // Register action callbacks in store so child components can trigger them
    this.maildeskStore.refreshMessages = () => this.refreshMessages();
    this.maildeskStore.loadMoreMessages = () => this.loadMoreMessages();
    this.maildeskStore.openComposer = (type, msg) => {
      if (type === "new") {
        this.openComposer();
      } else if (type === "reply") {
        this.openReplyComposer(msg);
      } else if (type === "replyAll") {
        this.openReplyAllComposer(msg);
      } else if (type === "forward") {
        this.openForwardComposer(msg);
      } else if (type === "draft") {
        this.openDraftComposer?.(msg);
      }
    };
    this.maildeskStore.selectMessage = (msg) => this.handleMessageClick(msg);
    this.maildeskStore.deleteMessages = (msgs) => {
      const messages = Array.isArray(msgs) ? msgs : [msgs];
      this.deleteMessagesOptimistic(messages);
    };
    this.maildeskStore.archiveMessages = (msgs) => this.handleBulkAction("archive", msgs);
    this.maildeskStore.markAsRead = (msgs) => this.handleBulkAction("markRead", msgs);
    this.maildeskStore.markAsUnread = (msgs) => this.handleBulkAction("markUnread", msgs);
    this.maildeskStore.toggleStar = (msgs) => this.handleBulkAction("toggleStar", msgs);
    this.maildeskStore.moveToFolder = (type, msgs) => this.handleBulkAction("move", Array.isArray(msgs) ? msgs : [msgs]);
    this.maildeskStore.openMoveDialog = (msgs) => this.openMoveToFolderDialog(Array.isArray(msgs) ? msgs : [msgs]);
    this.maildeskStore.openTagsDialog = (msg) => this.openTagAssignment(msg);
    this.maildeskStore.filterByAccount = (accountId) => this.handleAccountSelect(accountId);
    this.maildeskStore.filterByFolder = (folderId, accountId) => this.handleFolderSelect(folderId, accountId);
    this.maildeskStore.filterByTags = (tagIds) => {
      if (Array.isArray(tagIds)) {
        this.maildeskStore.setSelectedTagIds(tagIds);
      } else {
        this.handleTagSelect(tagIds);
      }
      this.refreshMessages();
    };
    this.maildeskStore.resetFilters = () => this.resetFilters();
    this.maildeskStore.clearContactFilter = () => this.clearContactFilter();
    this.maildeskStore.trustPartner = (msg) => this.trustPartner(msg);
    this.maildeskStore.createPartnerFromMessage = (msg) => this.createPartnerFromMessage(msg);
    this.maildeskStore.openContactSelector = () => this.openContactSelector();
    this.maildeskStore.fetchThread = (threadId, accountId) => this.fetchThread(threadId, accountId);

    onMounted(() => {
      // Start sync service: bus listeners + optional background sync polling
      this.syncService.startBusListeners();
      this.syncService.startPolling();
    });

    onWillUnmount(() => {
      // Cleanup sync service
      this.syncService.stopBusListeners();
      this.syncService.stopPolling();
    });
  }



  get selectedMessage() {
    return this.maildeskStore.selectedMessage;
  }

  get store() {
    return this.maildeskStore;
  }

  get currentFolderName() {
    const folderId = this.maildeskStore.currentFolderId;
    if (!folderId) {
      const filter = (this.maildeskStore.currentFilter || "").toLowerCase();
      if (filter === "incoming") return _t("Incoming");
      if (filter === "outgoing") return _t("Outgoing");
      return "Inbox";
    }
    const accId = this.maildeskStore.currentAccountId;
    const folders = this.maildeskStore.foldersByAccount[accId] || [];
    const find = (nodes) => {
      for (const f of nodes) {
        if (f.id === folderId) return f.name;
        if (f.children?.length) {
          const found = find(f.children);
          if (found) return found;
        }
      }
      return null;
    };
    return find(folders) || "Inbox";
  }


  // INITIAL DATA LOADING


  async loadInitialMessages() {
    const urlParams = this.getUrlParams();
    const actionParams = this.props.action?.params || {};

    let accountId = urlParams.get("account");
    let folderId = urlParams.get("folder");
    this.state.preselectMessageId = urlParams.get("message") || urlParams.get("mail") || null;

    // Apply action context params
    if (actionParams.partner_id) {
      this.maildeskStore.setPartnerId(actionParams.partner_id);
      this.maildeskStore.partnerName = actionParams.partner_name || "";
    }

    if (accountId) this.maildeskStore.setCurrentLocation(Number(accountId), folderId ? Number(folderId) : null);

    // Progressive Load:
    // 1. Accounts & Tags (Await this to have base structure)
    await this.fetchAccountsAndTags();

    // [AUTO-SELECT] If no account specified and we have accounts, select the first one
    if (!this.maildeskStore.currentAccountId && this.maildeskStore.accountsList?.length) {
      const firstAccount = this.maildeskStore.accountsList[0];
      // Default to null folder (will likely resolve to Inbox naturally or via subsequent logic)
      this.maildeskStore.setCurrentLocation(firstAccount.id, null);
      // [AUTO-EXPAND] Always expand the first account
      this.maildeskStore.expandFolder(`account_${firstAccount.id}`);
    }

    // 2. Folders (Fire and forget, render incrementally)
    this.fetchFoldersProgressively();

    // 3. Messages (Start fetching immediately, don't wait for all folders)
    // Server search uses folder_id directly, doesn't need tree.
    this.loadMoreMessages();

    // Context Unread Counts (if partner set via action/url)
    if (this.maildeskStore.partnerId) {
      this.fetchContextUnreadCounts();
    }

    // 4. Deep link check
    this.ensurePreselectedMessageLoaded();
  }

  async fetchAccountsAndTags() {
    this.maildeskStore.loading.accounts = true;
    try {
      const [accounts, tags] = await Promise.all([
        this.orm.call("mailbox.account", "get_account_list", []),
        this.orm.call("mail.message.tag", "get_tag_list", []),
      ]);
      this.maildeskStore.setAccounts(accounts || []);
      this.maildeskStore.setTags(tags || []);
      await this.syncService.ensureAccountChannels((accounts || []).map((a) => a.id));
    } catch (e) {
      console.error("Failed to load accounts:", e);
    } finally {
      this.maildeskStore.loading.accounts = false;
    }
  }

  applyLocationAfterFoldersLoaded() {
    const folderId = this.maildeskStore.currentFolderId;
    if (!folderId) return;

    const folder = this.maildeskStore.folders[folderId];
    if (!folder) return;

    const accId = Array.isArray(folder.account_id)
      ? folder.account_id[0]
      : folder.account_id;

    this.maildeskStore.currentAccountId = accId;

    this.maildeskStore.expandFolderParents(folderId);
  }

  async fetchFoldersProgressively() {
    const accounts = this.maildeskStore.accountsList;
    if (!accounts.length) return;

    // Initial accounts and folders load
    // Mark all accounts as loading using object spread (no Set.add)
    const loadingIds = {};
    for (const acc of accounts) {
      loadingIds[acc.id] = true;
    }
    this.maildeskStore.loading.folders = { ...loadingIds };

    // Parallel folder trees per account load
    accounts.forEach(async (acc) => {
      try {
        const folders = await this.orm.call("mailbox.account", "get_folder_tree", [acc.id]);
        this.maildeskStore.setFolders(acc.id, folders || []);

        this.applyLocationAfterFoldersLoaded();
      } catch (e) {
        console.error(`Failed to load folders for account ${acc.id}:`, e);
      } finally {
        // Immutable removal
        const { [acc.id]: _, ...remaining } = this.maildeskStore.loading.folders;
        this.maildeskStore.loading.folders = remaining;
      }
    });
  }

  ensureCurrentLocation() {
    if (!this.maildeskStore.currentAccountId) {
      const first = this.maildeskStore.accountsList[0];
      if (first) {
        this.maildeskStore.currentAccountId = first.id;
      }
    }

    if (
      this.maildeskStore.currentAccountId &&
      !this.maildeskStore.currentFolderId
    ) {
      // CRITICAL FIX: Do NOT force Inbox. Allow account-wide "All Messages".
      // this.autoSelectInbox(this.maildeskStore.currentAccountId);
      this.maildeskStore.expandFolder(`account_${this.maildeskStore.currentAccountId}`);
    }
  }

  autoSelectInbox(accountId) {
    // Folders index load
    const folders = this.maildeskStore.foldersByAccount[accountId];
    if (!folders) return;

    const findInbox = (list) => {
      if (!list) return null;
      for (const f of list) {
        if (f.folder_type === 'inbox') return f;
        if (f.children && f.children.length) {
          const found = findInbox(f.children);
          if (found) return found;
        }
      }
      return null;
    };

    const inbox = findInbox(folders);
    if (inbox) {
      this.maildeskStore.currentFolderId = inbox.id;
    }
  }

  async ensurePreselectedMessageLoaded() {
    const id = this.state.preselectMessageId;
    if (!id) return;

    const targetId = String(id);
    const messages = this.maildeskStore.currentMessages || [];
    let msg = messages.find(m => String(m.id) === targetId);

    if (msg) {
      this.maildeskStore.setSelectedMsgKey(msg.msg_key);
      this.state.preselectMessageId = null;
      return;
    }

    try {
      console.log(`[MailDesk] Deep link: Fetching message ${id}...`);
      const result = await this.orm.call("mailbox.account", "get_message_with_attachments", [{
        uid: id,
        account_id: this.maildeskStore.currentAccountId,
        folder_id: this.maildeskStore.currentFolderId,
      }]);

      if (result && (result.id || result.uid)) {
        const normalized = normalizeMessage(result, markup);
        this.maildeskStore.insertMessages([normalized]);
        this.maildeskStore.setSelectedMsgKey(normalized.msg_key);
      } else {
        this.notification.add(_t("Message not found"), { type: "warning" });
      }
    } catch (e) {
      console.error("[MailDesk] Deep link fetch failed", e);
    } finally {
      this.state.preselectMessageId = null;
    }
  }


  // MESSAGE LOADING


  async loadMoreMessages() {
    if (this.state.loadingMore) return;

    // Phase 4B: Check hasMore before loading
    if (this.state.messageOffset > 0 && !this.state.hasMore) {
      console.log("[MailDesk] No more messages to load");
      return;
    }

    // Initial load vs Pagination
    const isInitial = this.state.messageOffset === 0;

    this.state.loadingMore = true;
    this.maildeskStore.loading.messages = isInitial;

    try {
      const reqContextKey = this.maildeskStore._buildListContextKey?.() || "";
      const result = await this.orm.call("mailbox.sync", "message_search_load", [], {
        account_id: this.maildeskStore.currentAccountId,
        // Folder selection is always respected; filters (incoming/outgoing, tags, search)
        // further refine the query server-side.
        folder_id: this.maildeskStore.currentFolderId,
        filter: this.maildeskStore.currentFilter,
        search: this.maildeskStore.searchQuery,
        offset: this.state.messageOffset,
        limit: this.state.messageLimit,
        tag_ids: this.maildeskStore.selectedTagIds,
        partner_id: this.maildeskStore.partnerId,
      });

      if (result && result.records) {
        const activeContextKey = this.maildeskStore._buildListContextKey?.() || "";
        if (reqContextKey !== activeContextKey) {
          return;
        }
        const normalized = result.records.map((r) => normalizeMessage(r, markup));

        if (isInitial) {
          // Replace messages for initial load
          const inserted = this.maildeskStore.insertMessages(normalized, true);
          this.maildeskStore.setListResults?.(inserted.map((m) => m.msg_key).filter(Boolean), reqContextKey);
          this.maildeskStore.setListTotalCount?.(result.totalMessagesCount, reqContextKey);
        } else {
          // Append messages for pagination
          const inserted = this.maildeskStore.insertMessages(normalized, false);
          this.maildeskStore.appendListResults?.(inserted.map((m) => m.msg_key).filter(Boolean), reqContextKey);
          this.maildeskStore.setListTotalCount?.(result.totalMessagesCount, reqContextKey);
        }

        // Phase 4B: Track pagination metadata from backend
        this.state.hasMore = result.hasMore !== undefined ? result.hasMore : true;
        this.state.messageOffset += normalized.length;

        console.log(
          `[MailDesk] Loaded ${normalized.length} messages, offset now ${this.state.messageOffset}, hasMore: ${this.state.hasMore}`
        );
      }
    } finally {
      this.maildeskStore.loading.messages = false;
      this.state.loadingMore = false;
    }
  }

  async refreshMessages() {
    const previouslySelectedMessage = this.maildeskStore.selectedMessage;
    this.maildeskStore.resetListResults?.();
    this.state.messageOffset = 0;
    this.state.hasMore = true; // Phase 4B: Reset pagination state

    const promises = [this.loadMoreMessages()];

    // Context Unread Counts: Fetch if Partner Filter is active
    if (this.maildeskStore.partnerId && this.maildeskStore.currentAccountId) {
      promises.push(this.fetchContextUnreadCounts());
    } else {
      // If no partner filter, clear context counts (ensure Global Mode)
      this.maildeskStore.setContextUnreadCounts(null);
    }

    await Promise.all(promises);

    await this._ensureSelectedMessageRetained(previouslySelectedMessage);
  }

  async fetchContextUnreadCounts() {
    try {
      const counts = await this.orm.call("mailbox.sync", "get_context_unread_counts", [
        this.maildeskStore.currentAccountId,
        this.maildeskStore.partnerId
      ]);
      this.maildeskStore.setContextUnreadCounts(counts);
    } catch (e) {
      console.error("Failed to fetch context unread counts:", e);
    }
  }

  async _ensureSelectedMessageRetained(previousMessage) {
    if (!previousMessage) return;

    const accountId = Array.isArray(previousMessage.account_id)
      ? previousMessage.account_id[0]
      : previousMessage.account_id;
    const folderId = previousMessage.folder_id;
    const uid = previousMessage.uid || previousMessage.id;
    if (!accountId || !folderId || !uid) return;

    // Do not retain selection across location changes (e.g. switching to Drafts).
    // Retaining across folders can select a message that is not present in the
    // current list, making Drafts look "empty" or "not opening".
    if (accountId !== this.maildeskStore.currentAccountId || folderId !== this.maildeskStore.currentFolderId) {
      this.maildeskStore.setSelectedMsgKey(null);
      return;
    }

    try {
      // Use mailbox.sync (canonical) and preserve internal draft flag.
      const fetched = await this.orm.call("mailbox.sync", "get_message_with_attachments", [{
        uid,
        index_id: previousMessage.id,
        account_id: accountId,
        folder_id: folderId,
        is_internal_draft: !!previousMessage.is_local_draft,
      }]);
      try {
        const debug =
          window.__MAILDESK_DEBUG_ATTACHMENTS__ === true ||
          window.localStorage?.getItem("maildesk_debug_attachments") === "1";
        if (debug) {
          console.log("[MailDesk][RPC] OPEN MESSAGE payload attachments", fetched?.attachments);
          const first = fetched?.attachments?.[0];
          if (first) {
            console.log("[MailDesk][RPC] OPEN MESSAGE attachment keys", Object.keys(first).sort());
          }
        }
      } catch {
        // ignore
      }
      if (fetched && (fetched.id || fetched.uid)) {
        const normalized = normalizeMessage(fetched, markup);
        // Preserve the existing msg_key (especially important for internal drafts).
        if (previousMessage.msg_key) {
          normalized.msg_key = previousMessage.msg_key;
        }
        this.maildeskStore.insertMessages([normalized], false);
        if (previousMessage.msg_key) {
          this.maildeskStore.setSelectedMsgKey(previousMessage.msg_key);
        } else {
          this.maildeskStore.setSelectedMsgKey(normalized.msg_key);
        }
      } else if (previousMessage.msg_key) {
        this.maildeskStore.setSelectedMsgKey(previousMessage.msg_key);
      }
    } catch (e) {
      console.error("[MailDesk] Failed to retain selected message after refresh", e);
      if (previousMessage.msg_key) {
        this.maildeskStore.setSelectedMsgKey(previousMessage.msg_key);
      }
    }
  }





  // --- FolderTree handlers ---
  openComposer = () => {
    // Pattern mirrored from Odoo Mail: use global service, no dialog
    this.composerService.openComposer({
      mode: "new",
      accountId: this.maildeskStore.currentAccountId,
      onSent: () => this.refreshMessages(),
    });
  };

  handleFolderSelect = async (folderId, accountId) => {
    this.maildeskStore.setCurrentLocation(accountId, folderId);
    this.updateURLHash();
    await this.refreshMessages();
  };

  handleAccountSelect = async (accountId) => {
    this.maildeskStore.setCurrentLocation(accountId, null);
    // CRITICAL FIX: Do NOT auto-select Inbox.
    // This allows "Entire Account" scope (folder=null).
    // this.autoSelectInbox(accountId);
    this.updateURLHash();
    await this.refreshMessages();
  };

  handleTagSelect = async (tagId) => {
    if (tagId === null) {
      this.maildeskStore.setSelectedTagIds([]);
    } else {
      const current = this.maildeskStore.selectedTagIds || [];
      if (current.includes(tagId)) {
        this.maildeskStore.setSelectedTagIds(current.filter(id => id !== tagId));
      } else {
        this.maildeskStore.setSelectedTagIds([...current, tagId]);
      }
    }
    await this.refreshMessages();
  };

  clearContactFilter = async () => {
    this.maildeskStore.setPartnerId(null);
    await this.refreshMessages();
  };

  resetFilters = async () => {
    this.maildeskStore.setCurrentLocation(null, null);
    this.updateURLHash();
    await this.refreshMessages();
  };

  // Inflight guard: prevent duplicate parallel fetchThread calls
  _inflightThreadFetches = new Map();

  fetchThread = async (threadId, accountId) => {
    if (!threadId) return;

    // De-duplicate: if fetch already in flight, reuse that promise
    if (this._inflightThreadFetches.has(threadId)) {
      console.log(`[MailDesk] fetchThread ${threadId} already in flight, awaiting...`);
      return this._inflightThreadFetches.get(threadId);
    }

    const fetchPromise = (async () => {
      try {
        // Single RPC: open the entire thread (SSOT topology + cache-read + provider fetch on misses)
        const rawMessages = await this.orm.call("mailbox.sync", "open_thread_messages", [
          threadId,
          accountId || this.maildeskStore.currentAccountId,
        ]);

        // Normalize all thread messages with markup() for avatar_html rendering
        const messages = (rawMessages || []).map(m => normalizeMessage(m, markup));

        this.maildeskStore.setThreadMessages(threadId, messages);
        return messages;
      } catch (e) {
        console.error(
          "Failed to fetch thread:",
          e,
          e?.message,
          e?.stack
        );
        throw e;
      } finally {
        this._inflightThreadFetches.delete(threadId);
      }
    })();

    this._inflightThreadFetches.set(threadId, fetchPromise);
    return fetchPromise;
  };

  // --- MailList handlers ---
  handleMessageClick = async (msg) => {
    this.maildeskStore.setSelectedMsgKey(msg.msg_key);

    const accountId = msg.account_id?.[0] || this.maildeskStore.currentAccountId;
    const threadIdentifier = msg.thread_id || msg.message_id_norm;

    // Thread-first: opening a thread must NOT trigger N OpenMessage RPC calls.
    if (threadIdentifier) {
      this.maildeskStore.loading.messageBody = true;
      try {
        if (!this.maildeskStore.threadMessages[threadIdentifier]) {
          await this.fetchThread(threadIdentifier, accountId);
        }
        const thread = this.maildeskStore.threadMessages[threadIdentifier] || [];
        const selected = thread.find(m => m.id === msg.id);

        // Check if cached message has actual body content
        const hasBody = selected && (selected.body_html || selected.body_original);

        if (hasBody) {
          // Use cached thread message with body
          this.maildeskStore.updateMessageDetails(msg.msg_key, selected);
        } else if (!msg.body_original) {
          // Cache miss or no body: fetch from provider
          const result = await this.orm.call("mailbox.sync", "get_message_with_attachments", [{
            index_id: msg.id,
            uid: msg.uid || msg.id,
            account_id: accountId,
            folder_id: msg.folder_id || this.maildeskStore.currentFolderId,
            is_internal_draft: msg.is_local_draft,
          }]);
          if (result) {
            const normalized = normalizeMessage(result, markup);
            this.maildeskStore.updateMessageDetails(msg.msg_key, normalized);
            // Also update thread cache so next click doesn't refetch
            if (selected) {
              Object.assign(selected, normalized);
            }
          }
        }
      } catch (e) {
        console.error(
          "Failed to open thread:",
          e,
          e?.message,
          e?.stack
        );
      } finally {
        this.maildeskStore.loading.messageBody = false;
      }
    } else if (!msg.body_original) {
      // No thread id: open single message.
      this.maildeskStore.loading.messageBody = true;
      try {
        const result = await this.orm.call("mailbox.sync", "get_message_with_attachments", [{
          index_id: msg.id,
          uid: msg.uid || msg.id,
          account_id: accountId,
          folder_id: msg.folder_id || this.maildeskStore.currentFolderId,
          is_internal_draft: msg.is_local_draft,
        }]);
        try {
          const debug =
            window.__MAILDESK_DEBUG_ATTACHMENTS__ === true ||
            window.localStorage?.getItem("maildesk_debug_attachments") === "1";
          if (debug) {
            console.log("[MailDesk][RPC] OPEN MESSAGE payload attachments", result?.attachments);
            const first = result?.attachments?.[0];
            if (first) {
              console.log("[MailDesk][RPC] OPEN MESSAGE attachment keys", Object.keys(first).sort());
            }
          }
        } catch {
          // ignore
        }
        if (result) {
          this.maildeskStore.updateMessageDetails(msg.msg_key, normalizeMessage(result, markup));
        }
      } catch (e) {
        console.error(
          "Failed to load message details:",
          e,
          e?.message,
          e?.stack
        );
      } finally {
        this.maildeskStore.loading.messageBody = false;
      }
    } else {
      this.maildeskStore.loading.messageBody = false;
    }

    // Mark as read if unread
    if (!msg.is_read) {
      try {
        await this.orm.call("mailbox.sync", "set_flags", [[msg.id]], { is_read: true });
        this.maildeskStore.updateMessageFlags(msg.msg_key, { is_read: true });
      } catch (e) {
        console.error("Failed to mark read:", e);
      }
    }
  };

  handleFilterChange = async (filter) => {
    this.maildeskStore.setCurrentFilter(filter);
    await this.refreshMessages();
  };

  handleSearchChange = async (query) => {
    this.maildeskStore.setSearchQuery(query);
    await this.refreshMessages();
  };

  handleBulkAction = async (action, messages) => {
    const msgIds = messages.map(m => m.id);
    try {
      switch (action) {
        case "archive": {
          // CRITICAL: Use first message's account_id, not store's currentAccountId
          // This ensures archive works in both list view and thread view
          const firstMsg = messages[0];
          const accountId = Array.isArray(firstMsg?.account_id) ? firstMsg.account_id[0] : (firstMsg?.account_id || this.maildeskStore.currentAccountId);

          console.log("[ACTION] archive %d messages account=%s", messages.length, accountId);

          const archiveFolder = this.maildeskStore.findFolderByType?.(accountId, "archive");
          if (archiveFolder) {
            await this.orm.call("mailbox.sync", "move_messages_to_folder", [msgIds, archiveFolder.id]);
          }
          break;
        }
        case "delete":
          this.deleteMessagesOptimistic(messages);
          return; // Optimistic delete handles refresh logic internally (or doesn't need it)
        case "markRead":
          await this.orm.call("mailbox.sync", "set_flags", [msgIds], { is_read: true });
          messages.forEach(m => this.maildeskStore.updateMessageFlags(m.msg_key, { is_read: true }));
          break;
        case "markUnread":
          await this.orm.call("mailbox.sync", "set_flags", [msgIds], { is_read: false });
          messages.forEach(m => this.maildeskStore.updateMessageFlags(m.msg_key, { is_read: false }));
          break;
        case "toggleStar":
          for (const m of messages) {
            const newStarred = !m.is_starred;
            await this.orm.call("mailbox.sync", "set_flags", [[m.id]], { is_starred: newStarred });
            this.maildeskStore.updateMessageFlags(m.msg_key, { is_starred: newStarred });
          }
          break;
        case "move":
          this.openMoveToFolderDialog(messages);
          return;
      }
      if (["archive", "delete"].includes(action)) {
        await this.refreshMessages();
      }
    } catch (e) {
      console.error(`Bulk action ${action} failed:`, e);
      this.notification.add(_t("Action failed"), { type: "danger" });
    }
  };

  // --- MailDetail handlers ---
  openReplyComposer = (msg) => {
    // Pattern mirrored from Odoo Mail: global composer, no dialog
    // IMPORTANT: Use SSOT `message_index.id` for composer lookups.
    // `msg_key` can be "account||uid" in account-level (folder=null) scope,
    // which is not a stable key for SSOT (`uid` is only unique per folder).
    const composerMsgKey =
      msg?.id != null && Number.isFinite(Number(msg.id)) ? Number(msg.id) : msg.msg_key;
    this.composerService.openComposer({
      mode: "reply",
      msgKey: composerMsgKey,
      accountId: msg.account_id?.[0] || this.maildeskStore.currentAccountId,
      accounts: this.maildeskStore.accountsList,
      // THREADING: Pass parent message context for In-Reply-To/References headers
      replyToMessageId: msg.message_id || msg.message_id_norm || "",
      originalReferences: msg.references_hdr || "",
      threadId: msg.thread_id || "",
      // ODOO LINKAGE: Inherit model/res_id from parent
      model: msg.model || null,
      resId: msg.res_id || null,
    });
  };

  openReplyAllComposer = (msg) => {
    const composerMsgKey =
      msg?.id != null && Number.isFinite(Number(msg.id)) ? Number(msg.id) : msg.msg_key;
    this.composerService.openComposer({
      mode: "replyAll",
      msgKey: composerMsgKey,
      accountId: msg.account_id?.[0] || this.maildeskStore.currentAccountId,
      accounts: this.maildeskStore.accountsList,
      // THREADING: Pass parent message context
      replyToMessageId: msg.message_id || msg.message_id_norm || "",
      originalReferences: msg.references_hdr || "",
      threadId: msg.thread_id || "",
      // ODOO LINKAGE: Inherit model/res_id from parent
      model: msg.model || null,
      resId: msg.res_id || null,
    });
  };

  openForwardComposer = (msg) => {
    const composerMsgKey =
      msg?.id != null && Number.isFinite(Number(msg.id)) ? Number(msg.id) : msg.msg_key;
    this.composerService.openComposer({
      mode: "forward",
      msgKey: composerMsgKey,
      accountId: msg.account_id?.[0] || this.maildeskStore.currentAccountId,
      accounts: this.maildeskStore.accountsList,
      // THREADING: Forward does NOT inherit In-Reply-To/References (new thread start)
      // But we keep original message context for reference
      originalMessageId: msg.message_id || msg.message_id_norm || "",
      // ODOO LINKAGE: Optionally inherit model/res_id
      model: msg.model || null,
      resId: msg.res_id || null,
    });
  };

  openDraftComposer = (msg) => {
    // Open composer to edit an existing draft
    // Draft messages have uid format "draft-{id}" and contain pre-filled data
    if (!msg) return;

    // Extract draft ID from uid (format: "draft-123")
    const uidStr = String(msg.uid || "");
    const draftId = uidStr.startsWith("draft-")
      ? parseInt(uidStr.replace("draft-", ""), 10)
      : null;

    // Parse recipient strings to arrays of {email, name} objects
    const parseRecipients = (displayStr) => {
      if (!displayStr) return [];
      // Split by comma and parse each
      return displayStr.split(",").map(part => {
        const trimmed = part.trim();
        // Handle "Name <email>" format or just "email"
        const match = trimmed.match(/^(.+?)\s*<(.+?)>$/);
        if (match) {
          return { name: match[1].trim(), email: match[2].trim() };
        }
        return { email: trimmed, name: "" };
      }).filter(r => r.email);
    };

    this.composerService.openComposer({
      mode: "draft",
      draftMessageId: draftId,
      msgKey: msg.msg_key,
      accountId: msg.account_id?.[0] || this.maildeskStore.currentAccountId,
      accounts: this.maildeskStore.accountsList,
      // Pre-fill from draft data
      subject: msg.subject || "",
      to: parseRecipients(msg.to_display),
      cc: parseRecipients(msg.cc_display),
      bcc: parseRecipients(msg.bcc_display),
      body: msg.body_html || msg.body_original || "",
    });
  };

  deleteMessagesOptimistic = async (messages) => {
    if (!messages || messages.length === 0) return;

    const msgIds = messages.map(m => m.id);

    // Calculate unread delta for optimistic update
    let unreadDelta = 0;
    messages.forEach(m => {
      if (!m.is_read) unreadDelta++;
    });

    // Optimistic UI: Hide messages and update unread count
    this.maildeskStore.hideMessages(msgIds);
    this.maildeskStore.setSelectedMsgKey(null);

    if (unreadDelta > 0 && this.maildeskStore.currentFolderId) {
      const current = this.maildeskStore.unreadCounts[this.maildeskStore.currentFolderId] || 0;
      this.maildeskStore.setUnreadCount(this.maildeskStore.currentFolderId, Math.max(0, current - unreadDelta));
    }

    this.showUndoableTrashNotification(messages, unreadDelta);
  };

  showUndoableTrashNotification(messages, unreadDelta) {
    const textMoved = _t("Moved to Trash");
    const textUndo = _t("Undo");
    const msgIds = messages.map(m => m.id);

    this.state.undoToast = {
      message: textMoved,
      undoText: textUndo,
      onUndo: () => {
        // Revert logic
        this.maildeskStore.unhideMessages(msgIds);
        if (unreadDelta > 0 && this.maildeskStore.currentFolderId) {
          const current = this.maildeskStore.unreadCounts[this.maildeskStore.currentFolderId] || 0;
          this.maildeskStore.setUnreadCount(this.maildeskStore.currentFolderId, current + unreadDelta);
        }
      },
      onCommit: async () => {
        try {
          await this.orm.call("mailbox.sync", "delete_messages", [msgIds]);
          // Permanently remove from store
          messages.forEach(m => this.maildeskStore.deleteMessage(m.msg_key));
          this.maildeskStore.unhideMessages(msgIds);
        } catch (e) {
          console.error("[MailDesk] Undo commit failed", e);
          this.maildeskStore.unhideMessages(msgIds);
        }
      },
      onClose: () => {
        this.state.undoToast = null;
      }
    };
  }

  /**
   * Archive a single message (works for both list and thread context).
   * Uses msg.account_id explicitly - NOT currentAccountId.
   */
  archiveMessage = async (msg) => {
    try {
      // CRITICAL: Use message's account_id, not store's currentAccountId
      const accountId = Array.isArray(msg.account_id) ? msg.account_id[0] : (msg.account_id || this.maildeskStore.currentAccountId);

      console.log("[THREAD][ACTION] archive uid=%s account=%s", msg.uid, accountId);

      const archiveFolder = this.maildeskStore.findFolderByType?.(accountId, "archive");
      if (!archiveFolder) {
        this.notification.add(_t("Archive folder not found"), { type: "warning" });
        return;
      }
      await this.orm.call("mailbox.sync", "move_messages_to_folder", [[msg.id], archiveFolder.id]);
      this.maildeskStore.setSelectedMsgKey(null);
      await this.refreshMessages();

      // Undo notification
      this.notification.add(_t("Message archived"), {
        type: "info",
        buttons: [{
          name: _t("Undo"),
          onClick: async () => {
            const inboxFolder = this.maildeskStore.findFolderByType?.(accountId, "inbox");
            if (inboxFolder) {
              await this.orm.call("mailbox.sync", "move_messages_to_folder", [[msg.id], inboxFolder.id]);
              await this.refreshMessages();
            }
          },
        }],
      });
    } catch (e) {
      console.error("Archive failed:", e);
    }
  };

  toggleStar = async (msg) => {
    try {
      const newStarred = !msg.is_starred;
      await this.orm.call("mailbox.sync", "set_flags", [[msg.id]], { is_starred: newStarred });
      this.maildeskStore.updateMessageFlags(msg.msg_key, { is_starred: newStarred });
    } catch (e) {
      console.error("Toggle star failed:", e);
    }
  };

  markMessageRead = async (msg) => {
    try {
      await this.orm.call("mailbox.sync", "set_flags", [[msg.id]], { is_read: true });
      this.maildeskStore.updateMessageFlags(msg.msg_key, { is_read: true });
    } catch (e) {
      console.error("Mark read failed:", e);
    }
  };

  markMessageUnread = async (msg) => {
    try {
      await this.orm.call("mailbox.sync", "set_flags", [[msg.id]], { is_read: false });
      this.maildeskStore.updateMessageFlags(msg.msg_key, { is_read: false });
    } catch (e) {
      console.error("Mark unread failed:", e);
    }
  };

  trustPartner = async (msg) => {
    try {
      let partnerId = msg.avatar_partner_id;
      if (!partnerId) {
        // Auto-create partner if missing
        const name = msg.sender_display_name || msg.from_display || msg.email_from;
        const email = msg.email_from;
        if (!email) {
          this.notification.add(_t("Cannot create partner without email"), { type: "warning" });
          return;
        }

        // Optimistic creation
        const createdIds = await this.orm.create("res.partner", [{
          name: name,
          email: email,
        }]);
        partnerId = createdIds[0];

        // Update local message state
        if (partnerId) {
          this.maildeskStore.updateMessageDetails(msg.msg_key, { avatar_partner_id: partnerId });
        }
      }

      if (!partnerId) {
        this.notification.add(_t("No partner found for this sender"), { type: "warning" });
        return;
      }

	      await this.orm.call("res.partner", "trust_sender", [[partnerId]]);
	      this.maildeskStore.updateMessageFlags(msg.msg_key, { partner_trusted: true, content_trusted: true });
	      this.notification.add(_t("Sender trusted"), { type: "success" });
	    } catch (e) {
	      console.error("Trust failed:", e);
	      this.notification.add(_t("Failed to trust sender"), { type: "danger" });
    }
  };

  createPartnerFromMessage = async (msg) => {
    try {
      const action = await this.orm.call("mailbox.sync", "action_open_create_partner", [], {
        message_id: msg.id,
        email_from: msg.email_from,
        sender_display_name: msg.sender_display_name || msg.from_display,
      });
      if (action) {
        await this.action.doAction(action);
        if (action.context?.create_partner_return_to_maildesk) {
          await this.refreshMessages();
        }
      }
    } catch (e) {
      console.error("Failed to create partner from message:", e);
      this.notification.add(_t("Failed to open create partner form"), { type: "danger" });
    }
  };

  openContactSelector = () => {
    this.dialog.add(ContactPickerDialog, {
      onSelect: (partner) => {
        // partner is now full object {id, name, email, ...}
        // Handle both old (just id) and new (full object) formats for safety
        const partnerId = typeof partner === 'object' ? partner.id : partner;
        const partnerName = typeof partner === 'object' ? (partner.name || partner.email || "") : "";

        this.maildeskStore.setPartnerId(partnerId);
        this.maildeskStore.partnerName = partnerName;
        this.maildeskStore.setSearchQuery("");
        this.refreshMessages();
      },
    });
  };

  clearContactFilter = () => {
    this.maildeskStore.setPartnerId(null);
    this.maildeskStore.partnerName = "";
    this.maildeskStore.setSearchQuery("");
    this.refreshMessages();
  };

  printMessage = (msg) => {
    if (!msg) return;
    const printWindow = window.open("", "_blank");
    if (printWindow) {
      printWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head><title>${msg.subject || "Email"}</title></head>
        <body>
          <h2>${msg.subject || "(No Subject)"}</h2>
          <p><strong>From:</strong> ${msg.email_from || ""}</p>
          <p><strong>Date:</strong> ${msg.date || ""}</p>
          <hr/>
          ${msg.body_original || ""}
        </body>
        </html>
      `);
      printWindow.document.close();
      printWindow.print();
    }
  };

  openTagAssignment = (msg) => {
    const currentTagIds = (msg.tag_ids || []).map(t => typeof t === 'object' ? t.id : t);
    this.dialog.add(AssignTagsDialog, {
      tags: this.maildeskStore.tags || [],
      selectedTagIds: new Set(currentTagIds),
      onSelect: async (tagIds, { close, tags }) => {
        const msgId = parseInt(msg.id, 10);

        const selectedTags = tags || [];

        const existingIds = new Set((this.maildeskStore.tags || []).map(t => t.id));
        const addedTags = selectedTags.filter(t => !existingIds.has(t.id));
        if (addedTags.length > 0) {
          this.maildeskStore.setTags([...this.maildeskStore.tags, ...addedTags]);
        }

        close();

        try {
          await this.orm.call("mailbox.sync", "update_tags", [[msgId], tagIds]);

          const targetMsg = this.maildeskStore.messages[msg.msg_key];
          if (targetMsg) {
            const newTags = selectedTags.map(t => ({ id: t.id, name: t.name, color: t.color }));
            this.maildeskStore.updateMessageDetails(msg.msg_key, { tag_ids: newTags });
          }
        } catch (e) {
          console.error("Tag update failed:", e);
          this.notification.add(_t("Failed to update tags"), { type: "danger" });
        }
      },
    });
  };

  openMoveToFolderDialog = (msgOrMessages) => {
    const messages = Array.isArray(msgOrMessages) ? msgOrMessages : [msgOrMessages];
    const accountId = this.maildeskStore.currentAccountId;
    const folders = this.maildeskStore.getFoldersForAccount?.(accountId) || [];

    this.dialog.add(MoveToFolderDialog, {
      accounts: this.maildeskStore.accountsList,
      folders: folders,
      onSelect: async (folderId) => {
        const msgIds = messages.map(m => m.id);
        await this.orm.call("mailbox.sync", "move_messages_to_folder", [msgIds, folderId]);
        await this.refreshMessages();
      },
    });
  };


  // URL & ROUTING


  getUrlParams() {
    return new URLSearchParams(window.location.hash.slice(1));
  }

  updateURLHash() {
    const params = new URLSearchParams();
    if (this.maildeskStore.currentAccountId) params.set("account", this.maildeskStore.currentAccountId);
    if (this.maildeskStore.currentFolderId) params.set("folder", this.maildeskStore.currentFolderId);
    window.location.hash = params.toString();
  }


}

// Register as action
registry.category("actions").add("maildesk_mail_client.maildesk_action", MailDesk);
