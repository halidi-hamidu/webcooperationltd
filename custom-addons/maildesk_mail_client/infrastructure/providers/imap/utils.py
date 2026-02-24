# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP Utilities
"""


def has_attachments_from_bodystructure(node):
    """
    Recursively check BODYSTRUCTURE response for attachments.
    """

    def to_text(x, lower=True):
        if x is None:
            return ""
        if isinstance(x, (bytes, bytearray)):
            try:
                s = x.decode("utf-8", "ignore")
            except Exception:
                s = x.decode("latin-1", "ignore")
        else:
            s = str(x)
        return s.lower() if lower else s

    def params_pairs(p):
        if not p:
            return []
        if isinstance(p, dict):
            return list(p.items())
        if isinstance(p, (list, tuple)):
            if (
                len(p) == 2
                and not isinstance(p[0], (list, tuple))
                and not isinstance(p[1], (list, tuple))
            ):
                return [p]
            # Flatten flat list [key, val, key2, val2]
            res = []
            for i in range(0, len(p), 2):
                if i + 1 < len(p):
                    res.append((p[i], p[i + 1]))
            return res
        return []

    if not node:
        return False

    # Multipart
    if isinstance(node, (list, tuple)) and isinstance(node[0], (list, tuple)):
        # It's a multipart structure, iterate children
        for child in node:
            if isinstance(child, (list, tuple)):
                if has_attachments_from_bodystructure(child):
                    return True
        return False

    # Leaf node (body part)
    # Structure: [type, subtype, params, id, desc, encoding, size, lines, md5, disp, lang, loc]
    # Indices vary, but basic check is sufficient usually.
    # Check Content-Disposition first if available (index 8 or 9 often)

    # Convert node elements to text for loose checking
    # Usually: type=0, subtype=1, params=2, ..., disposition is often near end
    # disposition is typically (type, params) e.g. ("attachment", (filename "foo"))

    # We can walk the list and look for "attachment" tuple
    for item in node:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            disp_type = to_text(item[0])
            if disp_type == "attachment":
                return True
            if disp_type == "inline":
                # Check if it has filename
                params = params_pairs(item[1])
                for k, v in params:
                    if to_text(k) in ("filename", "name"):
                        return True

    return False
