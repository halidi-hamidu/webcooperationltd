# Web Selcom Integration

Selcom payment gateway integration for Odoo 19. All Selcom API logic lives in
a single **`Selcom`** service class (`models/selcom_client.py`).

## Structure

```
web_selcom_integration/
├── models/
│   ├── selcom_client.py     ← the single Selcom class (all endpoints)
│   ├── exceptions.py        ← Selcom* exception hierarchy
│   ├── res_partner.py       ← unique persistent till aliases
│   ├── selcom_order.py      ← local order/payment records
│   └── payment_transaction.py ← acquirer pipeline hook
├── controllers/main.py      ← /web_selcom/webhook (idempotent)
├── security/ir.model.access.csv
├── views/                   ← Selcom Orders menu + partner tab
└── tests/test_selcom.py
```

## The Selcom class

| Method | Endpoint | Purpose |
|---|---|---|
| `generate_till_alias(customer_id, existing)` | — | Unique, persisted, reused alias (`CUST-<id>-<hex>`) |
| `create_order(order)` | `POST /checkout/create-order` | Full order (cards need billing) |
| `create_minimal_order(order)` | `POST /checkout/create-order-minimal` | Non-card only |
| `cancel_order(order_id)` | `DELETE /checkout/cancel-order` | Refuses completed/cancelled |
| `get_order_status(order_id)` | `GET /checkout/order-status` | + application status mapping |
| `list_orders(from, to)` | `GET /checkout/list-orders` | Validates `YYYY-MM-DD` and range |
| `handle_webhook(payload)` | — | Idempotent, amount+currency verified |
| `encode_url` / `decode_url` | — | Base64 URL helpers (double-encode safe on decode) |
| `map_payment_status` | — | PENDING→pending, COMPLETED→paid, etc. |
| `generate_order_id` | — | `ORD-YYYYMMDD-XXXXXX` |
| `_make_request` / `_handle_response` | — | Shared signing/auth/error handling |

## Configuration (ir.config_parameter — never hard-coded)

| Key | Example |
|---|---|
| `web_selcom_integration.api_key` | `<from Selcom portal>` |
| `web_selcom_integration.api_secret` | `<from Selcom portal>` |
| `web_selcom_integration.base_url` | `https://selcom-payment-api.akamilab.com/v1` (dev/prod differ) |
| `web_selcom_integration.vendor_till` | `VENDORTILL` |

## Webhook

`POST /web_selcom/webhook` — updates `selcom.order`, idempotent by
order_id + gateway reference, verifies amount & currency before marking paid
(mismatches set `mismatch_flag` and keep the order pending).

## Security

- Credentials only from system parameters; never logged.
- Exceptions carry endpoint/http/resultcode but never secrets.
- Order is only `paid` after verified webhook or order-status COMPLETED —
  never on `create_order()` success.

## Tests

`tests/test_selcom.py` covers URL base64, status mapping, till alias
(create/reuse/duplicate), all endpoints (success + validation + auth/API
errors), and webhooks (valid/duplicate/rejected/amount-mismatch/
currency-mismatch/unknown-order).
