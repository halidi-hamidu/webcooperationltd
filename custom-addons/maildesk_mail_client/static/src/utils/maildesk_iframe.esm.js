// Copyright (C) 2025 Metzler IT GmbH
// License Odoo Proprietary License v1.0 (OPL-1)
// You may use this file only in accordance with the license terms.
// For more information, visit:
// https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

/** @odoo-module **/

/**
 * MailDesk MailDesk Iframe.
 *
 * Purpose: Defines frontend behavior used by the MailDesk OWL UI.
 */

/**
 * maildesk_iframe - Pure utility functions for iframe handling
 *
 * NO OWL dependencies (no hooks, no state).
 * Can be imported from any component or service.
 */

/**
 * Strip outer html/body tags from content if present.
 * Email content may come wrapped in full HTML document.
 *
 * @param {string} html - HTML content potentially wrapped in html/body
 * @returns {string} Just the body content
 */
function stripHtmlWrapper(html) {
    if (!html) return "";

    // Remove DOCTYPE
    let content = html.replace(/<!DOCTYPE[^>]*>/gi, "").trim();

    // Extract body content if html/body tags present
    const bodyMatch = content.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
    if (bodyMatch) {
        content = bodyMatch[1];
    }

    // Remove standalone html tags
    content = content.replace(/<\/?html[^>]*>/gi, "");
    content = content.replace(/<\/?head[^>]*>[\s\S]*?<\/head>/gi, "");

    return content.trim();
}

/**
 * Generate iframe srcdoc for email body display.
 *
 * @param {string} bodyHtml - HTML content to display
 * @param {Object} options - Configuration options
 * @param {boolean} options.trusted - If true, allow less restrictive sandbox
 * @returns {string} Complete HTML document for srcdoc
 */
export function generateIframeSrcdoc(bodyHtml, options = {}) {
    // Strip any existing html/body wrapper from email content
    const processedBody = stripHtmlWrapper(bodyHtml);

    return `<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            box-sizing: border-box;
        }
        html, body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            line-height: 1.5;
            background: white;
            overflow: hidden;
        }
        body {
            padding: 12px;
        }
        img {
            max-width: 100%;
            height: auto;
        }
        a {
            color: #0066cc;
        }
        blockquote {
            border-left: 3px solid #ccc;
            margin: 1em 0;
            padding-left: 1em;
            color: #666;
        }
        pre, code {
            background: #f5f5f5;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
            font-size: 13px;
        }
        pre {
            padding: 12px;
            overflow-x: auto;
        }
        table {
            max-width: 100%;
            border-collapse: collapse;
        }
        table td, table th {
            padding: 4px 8px;
        }
    </style>
</head>
<body>
    ${processedBody}
    <script>
        // Accurate height calculation
        function getContentHeight() {
            // Get actual content bounds
            const body = document.body;
            const html = document.documentElement;

            // Reset any scrolling
            body.style.overflow = 'visible';
            html.style.overflow = 'visible';

            // Method 1: offsetHeight (most reliable)
            const offsetHeight = body.offsetHeight;

            // Method 2: getBoundingClientRect
            const rect = body.getBoundingClientRect();
            const rectHeight = rect.height;

            // Method 3: Last element position
            let lastElementBottom = 0;
            const children = body.children;
            for (let i = 0; i < children.length; i++) {
                const child = children[i];
                if (child.tagName !== 'SCRIPT') {
                    const childRect = child.getBoundingClientRect();
                    const bottom = childRect.top + childRect.height;
                    if (bottom > lastElementBottom) {
                        lastElementBottom = bottom;
                    }
                }
            }
            // Add body padding
            const bodyStyle = getComputedStyle(body);
            const paddingTop = parseFloat(bodyStyle.paddingTop) || 0;
            const paddingBottom = parseFloat(bodyStyle.paddingBottom) || 0;
            lastElementBottom += paddingBottom;

            // Use maximum of methods for safety
            const height = Math.max(offsetHeight, rectHeight, lastElementBottom);

            return Math.ceil(height);
        }

        // Notify parent of height
        function notifyHeight() {
            const height = getContentHeight();
            parent.postMessage({ type: 'maildesk-iframe-height', height: height }, '*');
        }

        // Open links in parent window
        document.addEventListener('click', function(e) {
            const link = e.target.closest('a');
            if (link && link.href && !link.href.startsWith('javascript:')) {
                e.preventDefault();
                parent.postMessage({ type: 'maildesk-link-click', href: link.href }, '*');
            }
        });

        // Use ResizeObserver for robust height tracking
        function onReady() {
            // Notify immediately
            notifyHeight();

            // Watch for size changes
            if (window.ResizeObserver) {
                const resizeObserver = new ResizeObserver(function() {
                    notifyHeight();
                });
                resizeObserver.observe(document.body);
                resizeObserver.observe(document.documentElement);
            } else {
                // Fallback for very old environments (unlikely in Odoo 19 context)
                window.addEventListener('resize', notifyHeight);
                setInterval(notifyHeight, 500);
            }

            // Also watch for image loads specifically as they might shift layout
            // without immediately triggering observer in some edge cases
            const images = document.querySelectorAll('img');
            images.forEach(function(img) {
                if (!img.complete) {
                    img.addEventListener('load', notifyHeight);
                    img.addEventListener('error', notifyHeight);
                }
            });
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', onReady);
        } else {
            onReady();
        }
    </script>
</body>
</html>`;
}

/**
 * Get sandbox attribute value based on trust level.
 *
 * @param {boolean} trusted - Whether sender is trusted
 * @returns {string} Sandbox attribute value
 */
export function getIframeSandbox(trusted) {
    // Base sandbox always needs allow-scripts for height calculation
    const base = "allow-same-origin allow-scripts";
    if (trusted) {
        return `${base} allow-popups allow-popups-to-escape-sandbox`;
    }
    return base;
}
