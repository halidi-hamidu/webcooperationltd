import logging
from datetime import date

from odoo import http
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.web.controllers.home import Home
from odoo.http import request

from . import demo_data as demo

_logger = logging.getLogger(__name__)

PAGE_SIZE = 20

STATUS_FILTERS = {
    "all": None,
    "paid": "Paid",
    "pending": "Posted",
    "unpaid": "Posted",
    "overdue": "Overdue",
}

PROJECT_STATUS_KEYS = {s.lower().replace(" ", "_"): s for s in demo.PROJECT_STATUSES}


class WebPortalHome(Home):
    """Post-login redirection for portal users."""

    @http.route()
    def web_login(self, redirect=None, *args, **kw):
        """Override /web/login: send ALL portal users to the dashboard."""
        response = super().web_login(redirect=redirect, *args, **kw)
        if not request.session.uid:
            return response
        user = request.env["res.users"].browse(request.session.uid)
        if user.has_group("base.group_portal"):
            return request.redirect("/web_portal/dashboard")
        return response


class WebPortalDashboard(http.Controller):
    """Custom fleet dashboard for portal users (demo data during dev)."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _require_portal_partner(self):
        user = request.env.user
        if not user or user._is_public():
            return None
        return user.partner_id.commercial_partner_id

    def _demo_projects(self, partner):
        rows = []
        for i, (name, ref, status, start, end, desc) in enumerate(demo.PROJECTS, 1):
            vehicle = demo.VEHICLES[(i - 1) % len(demo.VEHICLES)]
            rows.append({
                "id": i,
                "name": name,
                "ref": ref,
                "status": status,
                "status_style": demo.PROJECT_STATUS_STYLES[status],
                "start_date": start,
                "end_date": end,
                "customer": partner.name,
                "description": desc,
                "vehicle_plate": vehicle[0],
                "vehicle_model": vehicle[1],
            })
        return rows

    def _demo_invoices(self, partner):
        rows = []
        for i, (num, dt, due, status, desc, total, paid) in enumerate(
                demo.INVOICES, 1):
            due_amt = total - paid
            overdue = status == "Overdue" or (
                status in ("Partially Paid",) and due and due < date.today())
            rows.append({
                "id": i,
                "name": num,
                "invoice_date": dt,
                "invoice_date_due": due,
                "customer": partner.name,
                "ref": desc,
                "amount_total": total,
                "amount_paid": paid,
                "amount_due": max(due_amt, 0),
                "state": status,
                "payment_state": status,
                "status": status,
                "status_style": demo.INVOICE_STATUS_STYLES[status],
                "badge_label": status,
                "badge_style": demo.INVOICE_STATUS_STYLES[status],
                "is_overdue": overdue,
                "currency": request.env.company.currency_id,
            })
        return rows

    def _paginate(self, rows, page):
        try:
            page = max(1, int(page))
        except (TypeError, ValueError):
            page = 1
        total = len(rows)
        pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
        page = min(page, pages)
        return rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE], page, pages, total

    def _keep_params(self, tab, **extra):
        params = {"tab": tab}
        params.update({k: v for k, v in extra.items() if v})
        return "&".join(f"{k}={v}" for k, v in params.items())

    # ------------------------------------------------------------------
    # dashboard (tabs: vehicles/projects + invoices)
    # ------------------------------------------------------------------
    @http.route("/web_portal/dashboard", type="http", auth="user", website=True)
    def dashboard(self, page=1, tab="invoices", **kw):
        partner = self._require_portal_partner()
        if not partner:
            return request.redirect("/web/login")

        tab = tab if tab in ("vehicles", "invoices") else "invoices"
        search = (kw.get("name") or "").strip()
        status = kw.get("status") or "all"
        date_from = kw.get("date_from") or ""
        date_to = kw.get("date_to") or ""

        invoices_all = self._demo_invoices(partner)
        projects_all = self._demo_projects(partner)

        # ---- metrics ----
        paid_total = sum(i["amount_total"] for i in invoices_all
                         if i["status"] == "Paid")
        unpaid_total = sum(i["amount_due"] for i in invoices_all
                           if i["status"] in ("Overdue", "Partially Paid"))
        pending_total = sum(i["amount_due"] for i in invoices_all
                            if i["status"] == "Posted")

        values = {
            "partner": partner,
            "tab": tab,
            "total_vehicles": len(demo.VEHICLES),
            "active_vehicles": sum(1 for v in demo.VEHICLES
                                   if v[2] == "Active"),
            "total_projects": len(projects_all),
            "paid_total": paid_total,
            "unpaid_total": unpaid_total,
            "pending_total": pending_total,
            "filters": {
                "name": search, "status": status,
                "date_from": date_from, "date_to": date_to,
            },
            "status_options": ["all"] + [s.lower().replace(" ", "_")
                                         for s in demo.INVOICE_STATUSES],
            "project_status_options": ["all"] + list(PROJECT_STATUS_KEYS.keys()),
        }

        def _match_date(d):
            if date_from and (not d or str(d) < date_from):
                return False
            if date_to and (not d or str(d) > date_to):
                return False
            return True

        if tab == "vehicles":
            rows = projects_all
            if search:
                rows = [r for r in rows if search.lower() in r["name"].lower()
                        or search.lower() in r["ref"].lower()]
            if status != "all":
                want = PROJECT_STATUS_KEYS.get(status)
                rows = [r for r in rows if r["status"] == want]
            if date_from:
                rows = [r for r in rows if r["start_date"]
                        and str(r["start_date"]) >= date_from]
            if date_to:
                rows = [r for r in rows if r["end_date"]
                        and str(r["end_date"]) <= date_to]
            paged, page, pages, total = self._paginate(rows, page)
            values.update({"projects": paged, "invoices": []})
        else:
            rows = invoices_all
            if search:
                rows = [r for r in rows if search.lower() in r["name"].lower()
                        or search.lower() in r["ref"].lower()]
            if status != "all":
                if status == "unpaid":
                    rows = [r for r in rows if r["status"] in
                            ("Posted", "Partially Paid")]
                else:
                    want = status.replace("_", " ").title()
                    rows = [r for r in rows if r["status"] == want]
            rows = [r for r in rows if _match_date(r["invoice_date"])]
            paged, page, pages, total = self._paginate(rows, page)
            values.update({"invoices": paged, "projects": []})

        values.update({"page": page, "pages": pages, "total": total})
        return request.render("web_portal.custom_portal_dashboard_layout", values)

    # ------------------------------------------------------------------
    # detail pages
    # ------------------------------------------------------------------
    @http.route("/web_portal/project/<int:project_id>", type="http",
                auth="user", website=True)
    def project_detail(self, project_id, **kw):
        partner = self._require_portal_partner()
        if not partner:
            return request.redirect("/web/login")
        projects = self._demo_projects(partner)
        project = next((p for p in projects if p["id"] == project_id), None)
        if not project:
            return request.not_found()
        return request.render("web_portal.portal_project_detail", {
            "partner": partner,
            "portal_project": project,
        })

    @http.route("/web_portal/invoice/<int:invoice_id>", type="http",
                auth="user", website=True)
    def invoice_detail(self, invoice_id, **kw):
        partner = self._require_portal_partner()
        if not partner:
            return request.redirect("/web/login")
        invoices = self._demo_invoices(partner)
        invoice = next((i for i in invoices if i["id"] == invoice_id), None)
        if not invoice:
            return request.not_found()
        return request.render("web_portal.portal_invoice_detail", {
            "partner": partner,
            "portal_invoice": invoice,
        })


class WebPortalCustomerPortal(CustomerPortal):
    """Route portal users away from the default /my home to the dashboard."""

    @http.route(["/my", "/my/home"], type="http", auth="user", website=True)
    def home(self, **kw):
        user = request.env.user
        if user.has_group("base.group_portal"):
            return request.redirect("/web_portal/dashboard")
        return super().home(**kw)
