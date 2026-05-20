/** @odoo-module **/
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";

function safeOnFocusin(fn) {
    return function (ev) {
        if (!ev || typeof ev.stopPropagation !== "function") {
            return;
        }
        return fn(ev);
    };
}

patch(Composer.prototype, {
    get wysiwygConfig() {
        const config = super.wysiwygConfig;
        if (config?.composerPluginDependencies?.onFocusin) {
            config.composerPluginDependencies.onFocusin = safeOnFocusin(
                config.composerPluginDependencies.onFocusin
            );
        }
        return config;
    },
});
