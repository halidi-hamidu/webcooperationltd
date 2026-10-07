# Customer Portal API

Secure REST API module for Odoo 19 exposing customer portal functionality for mobile / external applications.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | none | Portal user login, returns Bearer token |
| POST | `/api/v1/auth/logout` | Bearer | Invalidate current token |
| POST | `/api/v1/auth/reset-password` | none | Request password reset email (generic response) |
| GET | `/api/v1/customer/projects` | Bearer | List the customer's projects |
| GET | `/api/v1/customer/invoices` | Bearer | List the customer's invoices |

## Authentication

1. `POST /api/v1/auth/login` with `{"login": "...", "password": "..."}`.
2. Only **portal** users may authenticate (internal users are rejected).
3. Use the returned token on protected endpoints:

```
Authorization: Bearer <token>
```

Tokens are stored **hashed (SHA-256)** server-side, expire after a configurable TTL, and only one active token per user is allowed. Protected endpoints run with the portal user's environment, so Odoo record rules fully apply.

## Pagination

`GET /api/v1/customer/projects?page=1&limit=20` (limit capped at 100). Every list response includes:

```json
"pagination": {"page": 1, "limit": 20, "total": 45, "pages": 3}
```

## Invoice filters

- `status` — Odoo `state` (`draft`, `posted`, `cancel`)
- `date_from`, `date_to` — `YYYY-MM-DD` range on `invoice_date`

## Error format

```json
{"success": false, "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid username or password."}}
```

Codes: `INVALID_CREDENTIALS`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`, `RATE_LIMITED`, `INTERNAL_ERROR`.

## Security notes

- **No IDOR**: the customer is always derived from the authenticated token; client-supplied partner IDs are ignored.
- Brute-force protection: failed logins are tracked per-login and per-IP in `customer.portal.api.login.attempt`; threshold → HTTP 429.
- Password reset reuses Odoo's built-in expiring, signed reset-token flow (`_action_reset_password`); responses never reveal whether an account exists.
- Passwords and tokens are never logged.
- Use HTTPS in production (terminate TLS at your reverse proxy).
- Access rules for portal users on `project.project` / `account.move` are enforced by Odoo's standard portal record rules.

## Configuration (`ir.config_parameter`)

| Key | Default | Description |
|---|---|---|
| `customer_portal_api.token_ttl_seconds` | `86400` | Token lifetime (24h) |
| `customer_portal_api.rate_limit_window_minutes` | `15` | Failed-login window |
| `customer_portal_api.rate_limit_max_attempts` | `10` | Max failures in window |

## Running tests

```
odoo-bin -i customer_portal_api --test-enable --test-tags /customer_portal_api --stop-after-init -d testdb
```
