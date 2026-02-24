# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
IMAP MIME Structure Analyzer

Pure functions for analyzing IMAP BODYSTRUCTURE responses to determine
message characteristics like attachment presence.

No Odoo dependencies - protocol-level utilities.
"""


def has_attachments_from_bodystructure(node):
    """
    Analyze IMAP BODYSTRUCTURE to detect if message has attachments.

    Args:
        node: BODYSTRUCTURE response from IMAP server (nested list/tuple structure)

    Returns:
        bool: True if attachments detected, False otherwise
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
            pairs = []
            for it in p:
                if isinstance(it, (list, tuple)) and len(it) == 2:
                    pairs.append(it)
            return pairs
        return []

    def part_ct(part):
        if hasattr(part, "content_type"):
            return to_text(part.content_type)
        if isinstance(part, (list, tuple)) and len(part) >= 2:
            return f"{to_text(part[0])}/{to_text(part[1])}"
        return ""

    def part_params(part):
        if hasattr(part, "params"):
            return params_pairs(part.params)
        if isinstance(part, (list, tuple)) and len(part) >= 3:
            return params_pairs(part[2])
        return []

    def part_disp(part):
        if hasattr(part, "disposition"):
            return part.disposition
        if isinstance(part, (list, tuple)) and len(part) >= 9:
            return part[8]
        return None

    def part_disp_params(disp):
        if not disp:
            return []
        if isinstance(disp, (list, tuple)) and len(disp) >= 2:
            return params_pairs(disp[1])
        return []

    def part_disp_token(disp):
        if not disp:
            return ""
        if isinstance(disp, (list, tuple)) and len(disp) >= 1:
            return to_text(disp[0])
        return to_text(disp)

    def part_cid(part):
        if hasattr(part, "id"):
            return to_text(part.id)
        if isinstance(part, (list, tuple)) and len(part) >= 4:
            return to_text(part[3])
        return ""

    def has_name(pairs):
        for k, v in pairs:
            if to_text(k) in ("name", "filename") and v:
                return True
        return False

    def walk(n):
        if hasattr(n, "parts") and n.parts:
            for sp in n.parts:
                yield from walk(sp)
        elif isinstance(n, (list, tuple)) and n and isinstance(n[0], list):
            for sp in n[0]:
                yield from walk(sp)
        else:
            yield n

    for part in walk(node):
        ctype = part_ct(part)
        disp = part_disp(part)
        disp_tok = part_disp_token(disp)
        pparams = part_params(part)
        dparams = part_disp_params(disp)
        cid = part_cid(part)

        if disp_tok == "attachment":
            return True

        if has_name(pparams) or has_name(dparams):
            return True

        if (
            ctype
            and not ctype.startswith("text/")
            and not ctype.startswith("multipart/")
        ):
            return True

        if ctype.startswith("image/") and cid:
            return True

        if ctype.startswith("text/"):
            ext_like = any(
                ctype.endswith(suf)
                for suf in (
                    "/markdown",
                    "/x-markdown",
                    "/csv",
                    "/tab-separated-values",
                    "/plain; charset=us-ascii",
                )
            )
            if ext_like and (
                disp_tok in ("inline", "attachment")
                or has_name(pparams)
                or has_name(dparams)
            ):
                return True

    return False
