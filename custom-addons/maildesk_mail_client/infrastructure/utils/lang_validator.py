# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Language Validator - Validate and normalize language codes.

Provides functionality to validate language codes against active Odoo languages.
"""


def get_valid_lang(code, env):
    """
    Validate and normalize a language code.

    Args:
        code: Language code to validate
        env: Odoo environment

    Returns:
        Valid language code or False
    """
    if not code:
        return False

    Lang = env["res.lang"].sudo()

    lang = Lang.search([("code", "=", code), ("active", "=", True)], limit=1)
    if lang:
        return lang.code

    alt = f"{code}.UTF-8"
    lang = Lang.search([("code", "=", alt), ("active", "=", True)], limit=1)
    if lang:
        return lang.code

    lang_inactive = Lang.search([("code", "=", code)], limit=1)
    if lang_inactive:
        return False

    alt_inactive = Lang.search([("code", "=", alt)], limit=1)
    if alt_inactive:
        return False

    return False
