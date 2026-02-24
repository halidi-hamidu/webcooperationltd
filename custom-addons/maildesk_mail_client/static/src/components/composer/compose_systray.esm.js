// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Compose Systray.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

/**
 * ComposeSystray - Systray button to open a new composer.
 * Pattern mirrored from Odoo Mail: Uses global service instead of dialog.
 */
class ComposeSystray extends Component {
  static template = "maildesk_mail_client.ComposeSystray";
  static props = {};

  setup() {
    // Pattern mirrored from Odoo Mail: use global service for composer
    this.composerService = useService("maildesk.composer");
  }

  onClick() {
    // Open global composer via service (no dialog)
    this.composerService.openComposer({
      mode: "new",
    });
  }
}

user.hasGroup("maildesk_mail_client.group_mailbox_user").then((hasGroup) => {
  if (hasGroup) {
    registry.category("systray").add(
      "maildesk_mail_client.ComposeSystray",
      {
        Component: ComposeSystray,
      },
      { sequence: 99 }
    );
  }
}).catch(() => { });
