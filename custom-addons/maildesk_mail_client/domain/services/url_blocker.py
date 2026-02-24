# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Domain Service: Tracking URL and Pixel Detection.

Pure business logic for identifying and blocking tracking mechanisms in HTML content.
No dependencies on infrastructure or frameworks.
"""

import re
from html.parser import HTMLParser
from typing import Tuple
from urllib.parse import urlparse, parse_qs


class TrackingUrlDetector:
    """
    Domain service for detecting and blocking tracking URLs and pixels.

    Implements pattern matching for:
    - Tracking pixels (1x1 images)
    - Known tracker domains
    - Common tracking URL parameters
    """

    # Known tracking domains
    TRACKING_DOMAINS = {
        "google-analytics.com",
        "googletagmanager.com",
        "doubleclick.net",
        "facebook.com",
        "facebook.net",
        "mixpanel.com",
        "segment.com",
        "segment.io",
        "amplitude.com",
        "heap.io",
        "hotjar.com",
        "fullstory.com",
        "clarity.ms",
        "quantserve.com",
        "scorecardresearch.com",
        "outbrain.com",
        "taboola.com",
        "criteo.com",
    }

    # Tracking URL parameters
    TRACKING_PARAMS = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
        "msclkid",
        "mc_eid",
        "_hsenc",
        "mkt_tok",
        "yclid",
        "_ga",
        "campaignid",
    }

    def is_tracking_domain(self, url: str) -> bool:
        """Check if URL domain is a known tracker."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Check exact match or subdomain
            for tracker in self.TRACKING_DOMAINS:
                if domain == tracker or domain.endswith(f".{tracker}"):
                    return True

            # Check for common tracking path patterns
            if "/track" in parsed.path.lower() or "/pixel" in parsed.path.lower():
                return True

            return False
        except Exception:
            return False

    def is_tracking_pixel(
        self, img_src: str, width: str = "", height: str = ""
    ) -> bool:
        """
        Detect if image is a tracking pixel.

        Args:
            img_src: Image source URL
            width: Width attribute
            height: Height attribute
        """
        # 1x1 dimension check
        if width and height:
            try:
                w = int(re.sub(r"[^\d]", "", width))
                h = int(re.sub(r"[^\d]", "", height))
                if w == 1 and h == 1:
                    return True
            except (ValueError, TypeError):
                pass

        # Known tracker domain
        if self.is_tracking_domain(img_src):
            return True

        # Data URI 1x1 GIF
        if img_src.startswith("data:image/gif"):
            return True

        # Common pixel filenames
        pixel_patterns = ["/pixel", "/track", "/beacon", "/img.gif", "/clear.gif"]
        if any(pattern in img_src.lower() for pattern in pixel_patterns):
            return True

        return False

    def has_tracking_params(self, url: str) -> bool:
        """Check if URL contains tracking parameters."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)

            for param in params.keys():
                if param.lower() in self.TRACKING_PARAMS:
                    return True
            return False
        except Exception:
            return False

    def strip_tracking_params(self, url: str) -> str:
        """Remove tracking parameters from URL."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)

            # Remove tracking params
            clean_params = {
                k: v for k, v in params.items() if k.lower() not in self.TRACKING_PARAMS
            }

            # Rebuild query string
            if clean_params:
                query_parts = []
                for key, values in clean_params.items():
                    for value in values:
                        query_parts.append(f"{key}={value}")
                new_query = "&".join(query_parts)
            else:
                new_query = ""

            # Rebuild URL
            return parsed._replace(query=new_query).geturl()
        except Exception:
            return url


class TrackingBlockerHTMLParser(HTMLParser):
    """HTML parser that removes tracking pixels and cleans URLs."""

    def __init__(self, detector: TrackingUrlDetector):
        super().__init__()
        self.detector = detector
        self.output = []
        self.blocked_pixels = 0
        self.cleaned_urls = 0

    def handle_starttag(self, tag, attrs):
        """Process start tags, blocking pixels and cleaning URLs."""
        attrs_dict = dict(attrs)

        if tag == "img":
            src = attrs_dict.get("src", "")
            width = attrs_dict.get("width", "")
            height = attrs_dict.get("height", "")

            # Block tracking pixel
            if self.detector.is_tracking_pixel(src, width, height):
                self.blocked_pixels += 1
                # Replace with placeholder comment
                self.output.append("<!-- [Tracking pixel blocked] -->")
                return

        # Clean URLs in href attributes
        if tag == "a" and "href" in attrs_dict:
            href = attrs_dict["href"]
            if self.detector.has_tracking_params(href):
                clean_href = self.detector.strip_tracking_params(href)
                attrs_dict["href"] = clean_href
                self.cleaned_urls += 1

        # Rebuild tag with cleaned attributes
        attrs_str = " ".join(f'{k}="{v}"' for k, v in attrs_dict.items())
        if attrs_str:
            self.output.append(f"<{tag} {attrs_str}>")
        else:
            self.output.append(f"<{tag}>")

    def handle_endtag(self, tag):
        """Handle end tags (pass through unless pixel was blocked)."""
        self.output.append(f"</{tag}>")

    def handle_data(self, data):
        """Handle text data (pass through)."""
        self.output.append(data)

    def handle_startendtag(self, tag, attrs):
        """Handle self-closing tags."""
        attrs_dict = dict(attrs)

        if tag == "img":
            src = attrs_dict.get("src", "")
            width = attrs_dict.get("width", "")
            height = attrs_dict.get("height", "")

            if self.detector.is_tracking_pixel(src, width, height):
                self.blocked_pixels += 1
                self.output.append("<!-- [Tracking pixel blocked] -->")
                return

        attrs_str = " ".join(f'{k}="{v}"' for k, v in attrs_dict.items())
        if attrs_str:
            self.output.append(f"<{tag} {attrs_str} />")
        else:
            self.output.append(f"<{tag} />")

    def get_output(self) -> str:
        """Get cleaned HTML output."""
        return "".join(self.output)


def block_tracking_content(html: str) -> Tuple[str, int, int]:
    """
    Remove tracking pixels and clean URLs from HTML.

    Args:
        html: Original HTML content

    Returns:
        Tuple of (cleaned_html, blocked_pixels_count, cleaned_urls_count)
    """
    detector = TrackingUrlDetector()
    parser = TrackingBlockerHTMLParser(detector)

    try:
        parser.feed(html)
        return parser.get_output(), parser.blocked_pixels, parser.cleaned_urls
    except Exception:
        # If parsing fails, return original
        return html, 0, 0
