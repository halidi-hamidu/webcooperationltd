# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Mailbox Constants: Domain-level constants for mailbox logic.
"""

FOLDER_PRIORITY = {
    "INBOX": 0,
    "Sent": 1,
    "Gesendet": 1,
    "Gesendete Objekte": 1,
    "Archive": 2,
    "Archives": 2,
    "Drafts": 3,
    "Entwürfe": 3,
    "Trash": 99,
    "Gelöscht": 99,
    "Papierkorb": 99,
}
