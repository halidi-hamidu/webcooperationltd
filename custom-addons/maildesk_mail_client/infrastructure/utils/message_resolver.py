# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Message Resolver - Resolve message triplets (account, folder, UID).

Provides functionality to resolve message UIDs to account/folder/UID triplets.
"""


def resolve_message_triplet(any_id, explicit_folder_id, env):
    """
    Resolve message ID to (account_id, folder, uid) triplet.

    Args:
        any_id: Message UID or ID
        explicit_folder_id: Optional explicit folder ID
        env: Odoo environment

    Returns:
        Tuple of (account_id, folder_name, uid)
    """
    Index = env["maildesk.message_index"].sudo()
    s = str(any_id)

    rec = None
    if explicit_folder_id:
        Fld = env["mailbox.folder"].browse(explicit_folder_id)
        folder = Fld.imap_name or Fld.name or "INBOX"
        if Fld and Fld.account_id:
            rec = Index.search(
                [
                    ("account_id", "=", Fld.account_id.id),
                    ("folder", "=", folder),
                    ("uid", "=", s),
                ],
                limit=1,
            )
        if not rec:
            rec = Index.search([("folder", "=", folder), ("uid", "=", s)], limit=1)

    if not rec:
        accounts = env["mailbox.account"].search([("access_user_ids", "in", [env.uid])])
        domain = [("uid", "=", s)]
        if accounts:
            domain.insert(0, ("account_id", "in", accounts.ids))
        rec = Index.search(domain, order="id desc", limit=1)

    if rec:
        return rec.account_id.id, rec.folder or "INBOX", str(rec.uid)

    acc = env["mailbox.account"].search([("access_user_ids", "in", [env.uid])], limit=1)
    return acc.id if acc else False, "INBOX", s
