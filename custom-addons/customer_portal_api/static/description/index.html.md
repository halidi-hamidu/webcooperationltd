# Customer Portal API — Documentation

REST API for Odoo 19 exposing customer portal functionality (authentication, projects, invoices) to mobile or external applications.

- **Base URL:** `https://<your-odoo-domain>/api/v1`
- **Protocol:** HTTPS only in production
- **Format:** JSON (request and response bodies)
- **Authentication:** Bearer token obtained from the login endpoint

---

## Table of Contents

1. [Authentication](#authentication)
2. [Endpoints](#endpoints)
   - [Login](#1-login)
   - [Logout](#2-logout)
   - [Reset Password](#3-reset-password)
   - [Customer Projects](#4-customer-projects)
   - [Customer Invoices](#5-customer-invoices)
3. [Pagination](#pagination)
4. [Error Handling](#error-handling)
5. [Rate Limiting](#rate-limiting)
6. [Configuration](#configuration)
7. [Integration Examples](#integration-examples)

---

## Authentication

The API uses **Bearer token authentication**. Tokens are:

- Issued only to **portal users** (`base.group_portal`) — internal users are rejected.
- Stored server-side as SHA-256 hashes (the raw token is returned only once, at login).
- Valid for a configurable TTL (default 24 hours).
- Limited to **one active token per user** (a new login invalidates the old token).

Protected endpoints require this header:

```
Authorization: Bearer <token>
```

---

## Endpoints

### 1. Login

Authenticates a portal user and returns a session token.

```
POST /api/v1/auth/login
```

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `login` | string | Yes | Odoo username or email |
| `password` | string | Yes | Account password |

```json
{
  "login": "customer@example.com",
  "password": "customer_password"
}
```

**Success response — `200 OK`**

```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "user_id": 25,
    "partner_id": 103,
    "name": "John Doe",
    "email": "customer@example.com",
    "token": "AUTHENTICATION_TOKEN"
  }
}
```

| Field | Type | Description |
|---|---|---|
| `user_id` | int | Odoo user ID |
| `partner_id` | int | Customer (`res.partner`) ID |
| `name` | string | Display name |
| `email` | string | Email / login |
| `token` | string | Bearer token — store securely, shown only once |

**Error responses**

| Status | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Missing `login` or `password` |
| 401 | `INVALID_CREDENTIALS` | Wrong credentials, inactive account, or non-portal user |
| 429 | `RATE_LIMITED` | Too many failed attempts (see [Rate Limiting](#rate-limiting)) |
| 500 | `INTERNAL_ERROR` | Unexpected server error |

> The response is identical whether the login exists or the password is wrong — account existence is never revealed.

---

### 2. Logout

Invalidates the current token.

```
POST /api/v1/auth/logout
Authorization: Bearer <token>
```

**Success response — `200 OK`**

```json
{
  "success": true,
  "message": "Logged out",
  "data": null
}
```

| Status | Code | When |
|---|---|---|
| 401 | `UNAUTHORIZED` | Missing/expired/invalid token |

---

### 3. Reset Password

Requests a password-reset email.

```
POST /api/v1/auth/reset-password
```

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `email` | string | Yes | Account email/login |

```json
{
  "email": "customer@example.com"
}
```

**Response — `200 OK` (always identical)**

```json
{
  "success": true,
  "message": "If an account exists for this email, a password reset link has been sent."
}
```

The reset link reuses **Odoo's built-in signed, expiring reset-token mechanism** — no custom (insecure) token is generated. The response does not reveal whether the email exists.

| Status | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Missing `email` |
| 429 | `RATE_LIMITED` | Too many requests from this IP |

---

### 4. Customer Projects

Returns all projects belonging to the authenticated customer. Requires authentication.

```
GET /api/v1/customer/projects
Authorization: Bearer <token>
```

**Query parameters**

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number (≥ 1) |
| `limit` | int | 20 | Items per page (1–100) |

**Example**

```
GET /api/v1/customer/projects?page=1&limit=20
```

**Success response — `200 OK`**

```json
{
  "success": true,
  "data": [
    {
      "id": 10,
      "name": "Website Development",
      "customer_id": 103,
      "customer_name": "John Doe",
      "description": "Customer website project",
      "active": true
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 45,
    "pages": 3
  }
}
```

**Project fields**

| Field | Type | Description |
|---|---|---|
| `id` | int | Project ID |
| `name` | string | Project name |
| `customer_id` | int | Customer ID |
| `customer_name` | string | Customer name |
| `description` | string | Project description |
| `active` | bool | Whether the project is active |

> Projects include those where the customer (or their contact hierarchy) is the project customer **or** is a follower — matching what they see in the portal. Results are filtered by Odoo's portal record rules; no client-supplied `partner_id` is ever trusted.

---

### 5. Customer Invoices

Returns invoices belonging to the authenticated customer. Requires authentication.

```
GET /api/v1/customer/invoices
Authorization: Bearer <token>
```

**Query parameters**

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number |
| `limit` | int | 20 | Items per page (1–100) |
| `status` | string | — | Odoo state: `draft`, `posted`, `cancel` |
| `date_from` | date | — | Invoice date ≥ (`YYYY-MM-DD`) |
| `date_to` | date | — | Invoice date ≤ (`YYYY-MM-DD`) |

**Example**

```
GET /api/v1/customer/invoices?page=1&limit=20&status=posted&date_from=2026-01-01
```

**Success response — `200 OK`**

```json
{
  "success": true,
  "data": [
    {
      "id": 120,
      "invoice_number": "INV/2026/00120",
      "customer_id": 103,
      "customer_name": "John Doe",
      "invoice_date": "2026-10-01",
      "due_date": "2026-10-31",
      "currency": "USD",
      "subtotal": 1000.00,
      "tax": 180.00,
      "total": 1180.00,
      "amount_due": 1180.00,
      "amount_paid": 0.00,
      "status": "posted",
      "payment_state": "not_paid",
      "invoice_lines": [
        {
          "id": 301,
          "product": "Consulting",
          "description": "Consulting services",
          "quantity": 10,
          "unit_price": 100.0,
          "tax": 180.0,
          "subtotal": 1000.0,
          "total": 1180.0
        }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 1,
    "pages": 1
  }
}
```

**Invoice fields**

| Field | Type | Description |
|---|---|---|
| `id` | int | Invoice (move) ID |
| `invoice_number` | string | Sequence number |
| `invoice_date` / `due_date` | string | `YYYY-MM-DD` or empty |
| `currency` | string | Currency code/name |
| `subtotal` / `tax` / `total` | float | Amounts untaxed / tax / total |
| `amount_due` / `amount_paid` | float | Residual and paid amounts |
| `status` | string | `draft`, `posted`, `cancel` |
| `payment_state` | string | e.g. `not_paid`, `in_payment`, `paid`, `reversed` |
| `invoice_lines` | array | Invoice line details |

| Status | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Non-integer `page`/`limit` or invalid dates |
| 401 | `UNAUTHORIZED` | Missing/expired token |

---

## Pagination

All list endpoints accept `page` and `limit` and return metadata:

```json
"pagination": {
  "page": 1,
  "limit": 20,
  "total": 45,
  "pages": 3
}
```

- `limit` is capped at **100**.
- Default ordering: projects by `id desc`; invoices by `invoice_date desc, id desc`.

---

## Error Handling

All errors use a consistent envelope:

```json
{
  "success": false,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid username or password."
  }
}
```

| Code | HTTP | Meaning |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Invalid/missing request parameters |
| `INVALID_CREDENTIALS` | 401 | Login failed |
| `UNAUTHORIZED` | 401 | Missing, expired, or invalid token |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

---

## Rate Limiting

Failed logins are recorded in `customer.portal.api.login.attempt` and checked:

- **per login** (username/email), and
- **per client IP** (honours `X-Forwarded-For`).

Within the configured window, once failures reach the threshold, requests receive `429 RATE_LIMITED` for both login and reset-password endpoints. Passwords and tokens are never logged.

---

## Configuration

System parameters (`ir.config_parameter`, configurable in Settings → Technical → System Parameters):

| Key | Default | Description |
|---|---|---|
| `customer_portal_api.token_ttl_seconds` | `86400` | Token lifetime (24 h) |
| `customer_portal_api.rate_limit_window_minutes` | `15` | Failed-attempt window |
| `customer_portal_api.rate_limit_max_attempts` | `10` | Max failures before 429 |

---

## Integration Examples

### cURL

```bash
# Login
curl -s -X POST https://odoo.example.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login": "customer@example.com", "password": "customer_password"}'

# List invoices (use token from login)
curl -s https://odoo.example.com/api/v1/customer/invoices?page=1&limit=20 \
  -H "Authorization: Bearer <token>"
```

### Python (requests)

```python
import requests

BASE = "https://odoo.example.com/api/v1"

s = requests.Session()

r = s.post(f"{BASE}/auth/login", json={
    "login": "customer@example.com",
    "password": "customer_password",
})
r.raise_for_status()
token = r.json()["data"]["token"]

headers = {"Authorization": f"Bearer {token}"}

projects = s.get(f"{BASE}/customer/projects", params={"page": 1, "limit": 20}, headers=headers).json()
invoices = s.get(f"{BASE}/customer/invoices", params={"status": "posted"}, headers=headers).json()

# Logout (invalidates token)
s.post(f"{BASE}/auth/logout", headers=headers)
```

### JavaScript (fetch)

```javascript
const BASE = "https://odoo.example.com/api/v1";

async function login(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login: email, password }),
  });
  if (!res.ok) throw new Error((await res.json()).error.message);
  return (await res.json()).data.token;
}

async function getInvoices(token, params = {}) {
  const qs = new URLSearchParams({ page: 1, limit: 20, ...params }).toString();
  const res = await fetch(`${BASE}/customer/invoices?${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) throw new Error("Session expired");
  return res.json();
}
```

---

## Security Summary

- ✅ Customer always derived from the token — no client-supplied `partner_id` (no IDOR)
- ✅ Portal record rules enforced via the ORM (no raw SQL)
- ✅ Passwords never returned or logged; tokens stored hashed
- ✅ Generic responses prevent account enumeration (login & reset)
- ✅ Brute-force protection per login and per IP
- ✅ Password reset reuses Odoo's signed, expiring reset tokens
- ✅ HTTPS enforced at the reverse proxy in production
