# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""MailDesk Init.

Exports subpackages to register MailDesk components in Odoo.
Layer: infrastructure.
"""

from .client_factory import (
    get_outlook_access_token as get_outlook_access_token,
)
from .client_factory import (
    get_outlook_client as get_outlook_client,
)
from .client_factory import (
    is_outlook_account as is_outlook_account,
)
from .list_provider import (
    outlook_fetch_meta_batch as outlook_fetch_meta_batch,
)
from .list_provider import (
    outlook_get_folder_name as outlook_get_folder_name,
)
from .list_provider import (
    outlook_list_message_ids as outlook_list_message_ids,
)
from .list_provider import (
    outlook_query_from_filters as outlook_query_from_filters,
)
from .list_provider import (
    outlook_resolve_folder_id as outlook_resolve_folder_id,
)
from .list_provider import (
    outlook_resolve_folder_ids as outlook_resolve_folder_ids,
)
from .list_provider import (
    outlook_unread_counts as outlook_unread_counts,
)
from .message_provider import outlook_get_message_full as outlook_get_message_full
