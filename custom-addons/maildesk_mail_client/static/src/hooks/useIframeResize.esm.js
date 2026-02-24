// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk Useiframeresize.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * useIframeResize Hook
 *
 * Manages iframe height calculation with proper loading detection.
 * Replaces manual requestAnimationFrame + setTimeout hacks.
 *
 * Usage:
 *   const { iframeRef, triggerResize } = useIframeResize();
 *
 * TODO: Implement proper resize logic with:
 *   - onload handler
 *   - ResizeObserver for content changes
 *   - Cleanup on unmount
 */

import { useRef, onMounted, onWillUnmount } from "@odoo/owl";

export function useIframeResize() {
    const iframeRef = useRef("iframe");
    let resizeObserver = null;

    const resizeIframe = () => {
        const iframe = iframeRef.el;
        if (!iframe) return;

        try {
            const doc = iframe.contentDocument || iframe.contentWindow?.document;
            if (!doc) return;

            const height = Math.max(
                doc.body?.scrollHeight || 0,
                doc.documentElement?.scrollHeight || 0
            );
            iframe.style.height = `${height}px`;
        } catch (err) {
            console.warn("[useIframeResize] Cross-origin or access error:", err);
        }
    };

    onMounted(() => {
        const iframe = iframeRef.el;
        if (!iframe) return;

        // Resize on load
        iframe.addEventListener("load", resizeIframe);

        // Optional: ResizeObserver for dynamic content
        if (typeof ResizeObserver !== "undefined") {
            try {
                const doc = iframe.contentDocument || iframe.contentWindow?.document;
                if (doc?.body) {
                    resizeObserver = new ResizeObserver(resizeIframe);
                    resizeObserver.observe(doc.body);
                }
            } catch {
                // Cross-origin, skip observer
            }
        }
    });

    onWillUnmount(() => {
        const iframe = iframeRef.el;
        if (iframe) {
            iframe.removeEventListener("load", resizeIframe);
        }
        if (resizeObserver) {
            resizeObserver.disconnect();
            resizeObserver = null;
        }
    });

    return {
        iframeRef,
        triggerResize: resizeIframe,
    };
}
