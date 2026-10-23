## Selcom Create Till Alias API – Request and Response

**Date:** 23 October 2026

### 1. Request Sent to Selcom

**Endpoint:** `/checkout/create-till-alias`

**Request Payload:**
```json
{
  "vendor": "TILL60594876",
  "name": "Lunch Supplier",
  "memo": "CUST-6"
}
```

### 2. Response Received from Selcom

```json
{
  "reference": "S20779383931",
  "resultcode": "403",
  "result": "FAIL",
  "message": "API endpoint enabled for the vendor (4036)",
  "data": []
}
```


