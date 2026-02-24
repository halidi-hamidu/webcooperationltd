// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Debug Stats.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

export class DebugStats extends Component {
    static template = "maildesk_mail_client.DebugStatsComponent";
    static components = { Dropdown, DropdownItem };
    static props = {
        accountId: { type: Number, optional: true },
        folderId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            stats: null,
            loading: false,
        });
    }

    async loadStats() {
        if (this.state.loading) return;

        this.state.loading = true;
        try {
            const stats = await this.orm.call(
                "mailbox.sync",
                "get_debug_stats",
                [],
                {
                    account_id: this.props.accountId,
                    folder_id: this.props.folderId,
                }
            );
            this.state.stats = stats;
        } catch (error) {
            console.error("Failed to load debug stats:", error);
        } finally {
            this.state.loading = false;
        }
    }

    get hasStats() {
        return !!this.state.stats;
    }

    get indexCount() {
        return this.state.stats?.message_index_count || 0;
    }

    get cacheCount() {
        return this.state.stats?.ui_cache_count || 0;
    }

    get emailStateTotal() {
        return this.state.stats?.email_state_total || 0;
    }

    get deleteCount() {
        return this.state.stats?.email_state_delete || 0;
    }

    get moveCount() {
        return this.state.stats?.email_state_move || 0;
    }

    get flagCount() {
        return this.state.stats?.email_state_flags || 0;
    }

    get visibleEstimate() {
        return Math.max(0, this.indexCount - this.deleteCount - this.moveCount);
    }
}
