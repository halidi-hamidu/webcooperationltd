"""Shared response/error helpers for the Customer Portal API.

Follows the conventions of the `openapi` module: werkzeug JSON responses
with a consistent success/error envelope.
"""
import json
import logging

from odoo import fields
from odoo.http import Response, request

_logger = logging.getLogger(__name__)

# Error codes -> (http_status, default message)
ERROR_CODES = {
    "INVALID_CREDENTIALS": (401, "Invalid username or password."),
    "UNAUTHORIZED": (401, "Authentication required."),
    "FORBIDDEN": (403, "You do not have permission to access this resource."),
    "NOT_FOUND": (404, "Resource not found."),
    "VALIDATION_ERROR": (400, "Invalid request parameters."),
    "RATE_LIMITED": (429, "Too many requests. Please try again later."),
    "INTERNAL_ERROR": (500, "An unexpected error occurred."),
}


def json_response(status, payload):
    return Response(
        json.dumps(payload, default=str),
        status=status,
        content_type="application/json",
    )


def successful_response(status=200, data=None, message=None, pagination=None):
    payload = {"success": True}
    if message:
        payload["message"] = message
    payload["data"] = data
    if pagination:
        payload["pagination"] = pagination
    return json_response(status, payload)


def error_response(code, message=None, status=None):
    http_status, default_msg = ERROR_CODES.get(code, (500, "An unexpected error occurred."))
    payload = {
        "success": False,
        "error": {"code": code, "message": message or default_msg},
    }
    return json_response(status or http_status, payload)


def get_bearer_token():
    auth = request.httprequest.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return None


def authenticate():
    """Validate the Bearer token and return (user, error_response).

    Either user or error_response is set, never both.
    """
    token = get_bearer_token()
    if not token:
        return None, error_response("UNAUTHORIZED")
    user = request.env["customer.portal.api.token"].sudo().validate_token(token)
    if not user:
        return None, error_response("UNAUTHORIZED")
    # Rebind env to the authenticated user (non-sudo) so record rules apply.
    request.update_env(user=user)
    return user, None


def get_pagination_params():
    """Parse ?page=1&limit=20 query params with sane defaults/bounds."""
    try:
        page = max(1, int(request.params.get("page", 1)))
        limit = min(100, max(1, int(request.params.get("limit", 20))))
    except (TypeError, ValueError):
        return None, None, error_response(
            "VALIDATION_ERROR", "page and limit must be integers."
        )
    return page, limit, None


def pagination_meta(page, limit, total):
    pages = (total + limit - 1) // limit if limit else 0
    return {"page": page, "limit": limit, "total": total, "pages": pages}


def client_ip():
    xff = request.httprequest.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.httprequest.remote_addr or "unknown"


def parse_date(value, field_name, errors):
    try:
        return fields.Date.to_date(value)
    except Exception:
        errors.append(f"Invalid date for {field_name}: {value!r}")
        return None
