# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Domain helpers for ingestion queue behavior.
"""


def compute_backoff_minutes(retry_count: int, base_minutes: int = 5) -> int:
    """
    Compute exponential backoff in minutes based on retry count.
    """
    retry = retry_count if retry_count and retry_count > 0 else 0
    return int(base_minutes * (2**retry))
