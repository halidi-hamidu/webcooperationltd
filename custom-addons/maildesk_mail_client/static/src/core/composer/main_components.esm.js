// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Main Components.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

import { registry } from "@web/core/registry";
import { ComposerContainer } from "./composer_container.esm.js";

/**
 * Register ComposerContainer in main_components.
 * Pattern mirrored from Odoo Mail: odoo/addons/mail/static/src/core/main_components.js
 *
 * This ensures the component is mounted at Shell level,
 * outside of ActionManager, surviving navigation.
 */

registry.category("main_components").add("maildesk.ComposerContainer", {
    Component: ComposerContainer,
});
