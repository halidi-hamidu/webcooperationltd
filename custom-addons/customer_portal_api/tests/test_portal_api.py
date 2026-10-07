import json

from odoo import tests


@tests.tagged("post_install", "-at_install")
class TestCustomerPortalAPI(tests.HttpCase):
    """Tests for /api/v1 customer portal endpoints."""

    def setUp(self):
        super().setUp()
        self.password = "P0rtalT3st!x"
        self.customer = self.env["res.partner"].create(
            {"name": "API Test Customer", "email": "apitest.customer@example.com"}
        )
        self.other_customer = self.env["res.partner"].create(
            {"name": "Other Customer", "email": "other.customer@example.com"}
        )
        portal_group = self.env.ref("base.group_portal")
        self.portal_user = self.env["res.users"].create(
            {
                "name": "API Test Portal User",
                "login": "apitest.customer@example.com",
                "email": "apitest.customer@example.com",
                "password": self.password,
                "group_ids": [(6, 0, portal_group.ids)],
            }
        )
        self.project = self.env["project.project"].create(
            {
                "name": "API Test Project",
                "partner_id": self.customer.id,
            }
        )
        self.env["project.project"].create(
            {"name": "Other Customer Project", "partner_id": self.other_customer.id}
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _login(self):
        response = self.url_open(
            "/api/v1/auth/login",
            data=json.dumps({"login": self.portal_user.login, "password": self.password}),
            headers={"Content-Type": "application/json"},
        )
        return response

    def _get(self, url, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.url_open(url, headers=headers)

    # ------------------------------------------------------------------
    # auth
    # ------------------------------------------------------------------
    def test_login_success(self):
        res = self._login()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["user_id"], self.portal_user.id)
        self.assertEqual(body["data"]["partner_id"], self.customer.id)
        self.assertIn("token", body["data"])

    def test_login_wrong_password(self):
        res = self.url_open(
            "/api/v1/auth/login",
            data=json.dumps({"login": self.portal_user.login, "password": "wrong"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(res.status_code, 401)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "INVALID_CREDENTIALS")

    def test_login_internal_user_rejected(self):
        res = self.url_open(
            "/api/v1/auth/login",
            data=json.dumps({"login": "admin", "password": "admin"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertIn(res.status_code, (401, 429))
        if res.status_code == 401:
            self.assertEqual(res.json()["error"]["code"], "INVALID_CREDENTIALS")

    def test_endpoints_require_token(self):
        for url in ("/api/v1/customer/projects", "/api/v1/customer/invoices"):
            res = self._get(url)
            self.assertEqual(res.status_code, 401)
            self.assertEqual(res.json()["error"]["code"], "UNAUTHORIZED")

    def test_reset_password_generic_response(self):
        for email in ("apitest.customer@example.com", "nobody@nowhere.test"):
            res = self.url_open(
                "/api/v1/auth/reset-password",
                data=json.dumps({"email": email}),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(res.status_code, 200)
            self.assertIn("If an account exists", res.json()["message"])

    # ------------------------------------------------------------------
    # data endpoints
    # ------------------------------------------------------------------
    def test_projects_list(self):
        token = self._login().json()["data"]["token"]
        res = self._get("/api/v1/customer/projects?page=1&limit=20", token=token)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        names = [p["name"] for p in body["data"]]
        self.assertIn("API Test Project", names)
        self.assertNotIn("Other Customer Project", names)
        self.assertEqual(body["pagination"]["total"], 1)

    def test_invoices_list_isolation(self):
        # Create one invoice for the portal user's partner
        self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Test line",
                            "quantity": 1,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        token = self._login().json()["data"]["token"]
        res = self._get("/api/v1/customer/invoices", token=token)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        # Only this customer's invoices
        self.assertTrue(all(i["customer_id"] == self.customer.id for i in body["data"]))

    def test_invoices_bad_params(self):
        token = self._login().json()["data"]["token"]
        res = self._get("/api/v1/customer/invoices?page=abc", token=token)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["error"]["code"], "VALIDATION_ERROR")

    def test_token_invalidated_after_logout(self):
        token = self._login().json()["data"]["token"]
        res = self.url_open(
            "/api/v1/auth/logout",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        res = self._get("/api/v1/customer/projects", token=token)
        self.assertEqual(res.status_code, 401)
