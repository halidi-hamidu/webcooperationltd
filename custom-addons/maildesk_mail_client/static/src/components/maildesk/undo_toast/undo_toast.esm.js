// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Undo Toast.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { Component, onMounted, onWillUnmount } from "@odoo/owl";

export class UndoToast extends Component {
    static template = "maildesk_mail_client.UndoToast";
    static props = {
        message: String,
        undoText: String,
        onUndo: Function,
        onCommit: Function,
        onClose: Function,
        duration: { type: Number, optional: true },
    };
    static defaultProps = {
        duration: 5000,
    };

    setup() {
        this.timer = setTimeout(() => {
            if (!this.unmounted) {
                this.props.onCommit();
                this.props.onClose(); // Parent should unmount me
            }
        }, this.props.duration || 5000);

        onWillUnmount(() => {
            this.unmounted = true;
            if (this.timer) clearTimeout(this.timer);
        });
    }

    onUndoClick() {
        if (this.timer) clearTimeout(this.timer);
        this.props.onUndo();
        this.props.onClose();
    }
}
