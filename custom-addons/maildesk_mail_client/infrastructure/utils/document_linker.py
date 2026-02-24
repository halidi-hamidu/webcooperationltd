# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Document Linker - Find linked Odoo documents for email messages.

Provides functionality to find linked mail.message records based on
message-id and in-reply-to headers.
"""


def find_linked_document(message_id, in_reply_to, env):
    """
    Find a linked mail.message document for an email.

    Args:
        message_id: The Message-ID header value
        in_reply_to: The In-Reply-To header value
        env: Odoo environment

    Returns:
        Linked mail.message record or False
    """
    MailMessage = env["mail.message"].sudo()

    token1 = (message_id or "").strip("<>")
    token2 = (in_reply_to or "").strip("<>")

    def find(token):
        if not token:
            return False
        return MailMessage.search(
            [("message_id", "ilike", token)],
            order="id desc",
            limit=1,
        )

    rec = False
    if token2:
        rec = find(token2)
    if not rec and token1:
        rec = find(token1)

    if not rec:
        return False, False

    return rec.model, rec.res_id
