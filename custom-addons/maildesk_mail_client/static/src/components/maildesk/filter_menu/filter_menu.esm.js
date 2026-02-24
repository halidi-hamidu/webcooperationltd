// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Filter Menu.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { Component } from "@odoo/owl";

export class FilterMenu extends Component {
    static template = "maildesk_mail_client.FilterMenu";
    static props = {
        items: Array, // [{id, label}, ...]
        onSelect: Function,
        close: Function, // Provided by usePopover
    };

    onItemClick(item) {
        this.props.onSelect(item.id);
        this.props.close();
    }
}
