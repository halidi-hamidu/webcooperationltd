// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Thread Container.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * ThreadContainer Component
 *
 * Renders a list of ThreadMessage components for conversation history.
 * Placed ABOVE the current MailDetail message.
 */

import { Component } from "@odoo/owl";
import { ThreadMessage } from "../thread_message/thread_message.esm.js";

export class ThreadContainer extends Component {
    static template = "maildesk_mail_client.ThreadContainerComponent";
    static components = { ThreadMessage };
    static props = {
        messages: Array,
    };
}
