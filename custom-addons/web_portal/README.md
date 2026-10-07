# Web Portal (Fleet Customer Dashboard)

Custom Odoo 19 portal module for fleet management customers.

## What it does

- **Post-login redirection** — portal users whose partner is linked to fleet vehicles (as driver or manager, including child contacts) are redirected from `/web/login` to `/web_portal/dashboard` instead of `/my/home`.
- **Dark-themed dashboard** (`/web_portal/dashboard`) inheriting `portal.portal_layout`:
  - Welcome banner ("Welcome back, &lt;Company&gt;")
  - 4 stat cards: Total Vehicles (+ active count), Paid / Unpaid (overdue) / Pending invoice totals
  - Tabs (Vehicles / Invoices) + filter strip: invoice number search, status (`all|paid|pending|unpaid|overdue`), date range, green Filter button, Reset link
  - Invoices table with dynamic status badges (Paid / Pending / Unpaid / Overdue / Partially Paid), 👁 View link to `/my/invoices/<id>`, and 💳 Pay Invoice button when a residual remains
  - Pagination (20/page)

## Install

```
Apps → search "Web Portal" → Install
```

## Vehicle ↔ customer mapping

Vehicles are linked to the customer when the partner (or one of its contacts, `child_of`) is the vehicle's **driver** or **manager**. Adjust `_fleet_vehicle_domain` in `controllers/main.py` and the matching ir.rule in `security/web_portal_security.xml` if you use a different link (e.g. a custom `x_fleet_company_id` field).

## Security

- Route is `auth="user"`; the partner is always derived from the logged-in user (`commercial_partner_id`) — no client-supplied IDs.
- Added a portal record rule granting read-only access to `fleet.vehicle` records linked to their company.
- Invoice access relies on Odoo's standard portal record rules on `account.move`.
