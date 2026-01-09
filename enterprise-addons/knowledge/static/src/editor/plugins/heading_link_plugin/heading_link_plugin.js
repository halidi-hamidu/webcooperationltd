import { Plugin } from "@html_editor/plugin";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { ancestors, descendants } from "@html_editor/utils/dom_traversal";
import { scrollAndHighlightHeading } from "@html_editor/utils/url";
import { xml } from "@odoo/owl";
import { renderToElement } from "@web/core/utils/render";

export class HeadingLinkPlugin extends Plugin {
    static id = "headingLink";
    static dependencies = ["localOverlay", "history"];
    resources = {
        /** Handlers */
        start_edition_handlers: this.onStartEdition.bind(this),
        normalize_handlers: (root) => this.updateHeadingIds(root),
        clean_for_save_handlers: ({ root }) => this.cleanForSave(root),
        after_split_element_handlers: ({ secondPart }) => this.onAfterSplitElement(secondPart),

        system_classes: ["o-highlight-heading"],
    };

    setup() {
        // Create an overlay with the anchor.
        this.headingLinkOverlay = this.dependencies.localOverlay.makeLocalOverlay("o-heading-link-overlay");
        this.headingLinkContainer = renderToElement(xml`
            <div class="d-flex">
                <a href="#" title="${_t("Copy a link to this heading to the clipboard")}" class="o-heading-link fa fa-link"/>
            </div>
        `);
        this.headingLink = this.headingLinkContainer.firstElementChild;
        this.headingLinkOverlay.append(this.headingLinkContainer);
        this.headingLinkOverlay.style.visibility = "hidden";
        this.addDomListener(this.headingLink, "click", () => {
            const headingId = this.currentHeading?.getAttribute("data-heading-link-id");
            // Navigate to the heading and add the url to the clipboard.
            browser.location.hash = headingId;
            browser.navigator.clipboard.writeText(browser.location.href);
            // Add a step to the history and make sure the ID is saved.
            this.dependencies.history.addStep();
            // Highlight the heading.
            scrollAndHighlightHeading(this.editable, headingId);
        });
        this.addDomListener(this.headingLink, "dragstart", ev => ev.preventDefault());

        this.addDomListener(this.editable, "mousemove", this.onMousemove, true);
        this.updateHeadingIds();
    }

    onStartEdition() {
        scrollAndHighlightHeading(this.editable);
    }

    onMousemove(ev) {
        const heading = ev.target?.closest?.("h1, h2, h3, h4, h5, h6");
        if (heading?.textContent) {
            this.currentHeading = heading;
            // Resetting the position of the overlay.
            this.headingLinkOverlay.style.top = "0px";
            this.headingLinkOverlay.style.left = "0px";
            const containerRect = this.headingLinkContainer.getBoundingClientRect();
            // Get the range rectangle to position the overlay after it.
            const range = this.document.createRange();
            range.selectNodeContents(this.currentHeading);
            const rangeRect = range.getBoundingClientRect();
            // Position the overlay.
            this.headingLinkOverlay.style.top = `${rangeRect.top - containerRect.top + ((rangeRect.height - containerRect.height) / 2) + 2}px`;
            this.headingLinkOverlay.style.left = `${rangeRect.right - containerRect.left + 5}px`;
            this.headingLinkOverlay.style.visibility = "visible";
        } else {
            this.headingLinkOverlay.style.visibility = "hidden";
        }
    }

    cleanForSave(root) {
        for (const el of root.querySelectorAll(".o-highlight-heading")) {
            el.classList.remove("o-highlight-heading");
        }
    }

    onAfterSplitElement(secondPart) {
        // Ensure the ID doesn't get cloned.
        secondPart?.removeAttribute("data-heading-link-id");
    }

    /**
     * @param {Element} [root]
     */
    updateHeadingIds(root = this.editable) {
        const headings = [root, ...ancestors(root, this.editable), ...descendants(root)]
            .filter(node => node && /^H\d$/.test(node.nodeName));
        for (const heading of [...new Set(headings)]) {
            const headingId = heading.getAttribute("data-heading-link-id");
            if (!headingId) {
                heading.setAttribute("data-heading-link-id", "" + Math.floor(Math.random() * Date.now()));
            }
        }
    }
}
