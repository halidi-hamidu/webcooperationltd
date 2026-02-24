# Copyright (C) 2025 Metzler IT GmbH
# License Odoo Proprietary License v1.0 (OPL-1)
# You may use this file only in accordance with the license terms.
# For more information, visit:
# https://www.odoo.com/documentation/19.0/legal/licenses/licenses.html#odoo-proprietary-license

"""
Infrastructure Repositories

This package contains repository implementations that isolate Odoo ORM access.
Repositories are the ONLY layer allowed to touch env["model.name"].

Following Clean Architecture / Onion Architecture principles:
- Use cases depend on protocols (not repositories)
- Adapters call repositories (not ORM directly)
- Repositories encapsulate all ORM knowledge
"""
