# Copyright 2017 LasLabs Inc.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


def post_init_hook(env):
    # env = api.Environment(cr, SUPERUSER_ID, {})
    env["res.partner"]._install_partner_firstname()
