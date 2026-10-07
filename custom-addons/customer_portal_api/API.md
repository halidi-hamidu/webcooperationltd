# Customer Portal API — Documentation

Full API reference lives in [`static/description/API.md`](static/description/API.md).

Quick reference:

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | none | Portal user login → Bearer token |
| POST | `/api/v1/auth/logout` | Bearer | Invalidate current token |
| POST | `/api/v1/auth/reset-password` | none | Request reset email (generic response) |
| GET | `/api/v1/customer/projects` | Bearer | List customer's projects (paginated) |
| GET | `/api/v1/customer/invoices` | Bearer | List customer's invoices (paginated, filterable) |

Authentication: `Authorization: Bearer <token>` — tokens are SHA-256-hashed server-side, expire (default 24 h), one active token per user, portal users only.
