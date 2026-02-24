// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Toolbar.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * Toolbar Component
 *
 * Unified action toolbar for both bulk selection (MailList) and single message (MailDetail).
 * Visual only - all actions delegated to parent via onAction prop.
 */

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { DebugStats } from "../debug_stats/debug_stats.esm.js";

export class Toolbar extends Component {
    static template = "maildesk_mail_client.ToolbarComponent";
    static components = { DebugStats };
    static props = {
        mode: { type: String },  // "bulk" | "single"
        selectedCount: { type: Number, optional: true },
        message: { type: Object, optional: true },
        onAction: { type: Function },
        accountId: { type: Number, optional: true },
        folderId: { type: Number, optional: true },
    };





    get isBulkMode() {
        return this.props.mode === "bulk";
    }

    get isSingleMode() {
        return this.props.mode === "single";
    }

    get hasMessage() {
        return !!this.props.message;
    }

    get isStarred() {
        return this.props.message?.is_starred || false;
    }

    get isRead() {
        return this.props.message?.is_read || false;
    }





    onReply() {
        this.props.onAction?.("reply");
    }

    onReplyAll() {
        this.props.onAction?.("replyAll");
    }

    onForward() {
        this.props.onAction?.("forward");
    }

    onArchive() {
        this.props.onAction?.("archive");
    }

    onDelete() {
        this.props.onAction?.("delete");
    }

    onToggleStar() {
        this.props.onAction?.("toggleStar");
    }

    onMarkRead() {
        this.props.onAction?.("markRead");
    }

    onMarkUnread() {
        this.props.onAction?.("markUnread");
    }

    onMove() {
        this.props.onAction?.("move");
    }

    onTagAssign() {
        this.props.onAction?.("tagAssign");
    }

    onPrint() {
        this.props.onAction?.("print");
    }
}
