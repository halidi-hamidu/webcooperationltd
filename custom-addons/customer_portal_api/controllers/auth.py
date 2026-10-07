import logging

from odoo import http
from odoo.http import request

from ..helpers import (
    client_ip,
    error_response,
    json_response,
    successful_response,
)
from .helpers import authenticate

_logger = logging.getLogger(__name__)


class CustomerPortalApiAuth(http.Controller):

    @http.route("/api/v1/auth/login", type="http", auth="public", csrf=False,
                methods=["POST"])
    def login(self, **kwargs):
        try:
            body = self._json_body()
            login = (body.get("login") or "").strip()
            password = body.get("password") or ""
            if not login or not password:
                return error_response(
                    "VALIDATION_ERROR", "login and password are required."
                )

            Attempt = request.env["customer.portal.api.login.attempt"].sudo()
            ip = client_ip()
            # Brute-force protection: per-login and per-IP rate limiting
            if Attempt._is_limited(f"login:{login}") or Attempt._is_limited(f"ip:{ip}"):
                return error_response("RATE_LIMITED")

            try:
                uid = request.session.authenticate(request.db, login, password)
            except Exception:
                uid = None
            if not uid:
                Attempt.register(login, ip, False)
                _logger.info("Portal API login failed for login=%r ip=%s", login, ip)
                return error_response("INVALID_CREDENTIALS")

            user = request.env["res.users"].sudo().browse(uid)
            if not user.has_group("base.group_portal"):
                # Not a portal user — revoke session, generic failure
                request.session.logout()
                Attempt.register(login, ip, False)
                _logger.info("Portal API login rejected (non-portal) uid=%s", uid)
                return error_response("INVALID_CREDENTIALS")

            Attempt.register(login, ip, True)
            request.session.logout()  # API uses tokens, not cookie sessions

            token = request.env["customer.portal.api.token"].sudo().create_for_user(user)
            partner = user.partner_id
            return successful_response(
                message="Login successful",
                data={
                    "user_id": user.id,
                    "partner_id": partner.id,
                    "name": partner.name or user.name,
                    "email": partner.email or user.login,
                    "token": token,
                },
            )
        except Exception:
            _logger.exception("Portal API login error")
            return error_response("INTERNAL_ERROR")

    @http.route("/api/v1/auth/logout", type="http", auth="public", csrf=False,
                methods=["POST"])
    def logout(self, **kwargs):
        user, err = authenticate()
        if err:
            return err
        token = request.httprequest.headers.get("Authorization", "")[7:].strip()
        request.env["customer.portal.api.token"].sudo().search([
            ("token_hash", "=", request.env["customer.portal.api.token"].sudo()._hash_token(token)),
        ]).write({"active": False})
        return successful_response(message="Logged out")

    @http.route("/api/v1/auth/reset-password", type="http", auth="public", csrf=False,
                methods=["POST"])
    def reset_password(self, **kwargs):
        generic = {
            "success": True,
            "message": "If an account exists for this email, a password reset link has been sent.",
        }
        try:
            body = self._json_body()
            email = (body.get("email") or "").strip().lower()
            if not email:
                return error_response("VALIDATION_ERROR", "email is required.")
            Attempt = request.env["customer.portal.api.login.attempt"].sudo()
            if Attempt._is_limited(f"ip:{client_ip()}"):
                return error_response("RATE_LIMITED")

            users = request.env["res.users"].sudo().search([
                ("login", "=ilike", email),
                "|", ("active", "=", True), ("active", "=", False),
            ])
            portal_users = users.filtered(lambda u: u.has_group("base.group_portal"))
            if portal_users:
                try:
                    # Reuse Odoo's built-in, expiring, signed reset-token flow
                    portal_users[0]._action_reset_password()
                except Exception:
                    _logger.exception(
                        "Failed to send password reset email for login=%r", email)
            else:
                # Always respond generically — never reveal account existence
                _logger.info("Password reset requested for unknown login=%r", email)
            return json_response(200, generic)
        except Exception:
            _logger.exception("Portal API reset-password error")
            return json_response(200, generic)

    def _json_body(self):
        try:
            return request.get_json_data() or {}
        except Exception:
            return {}
