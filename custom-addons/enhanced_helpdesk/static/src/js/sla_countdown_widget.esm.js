/** @odoo-module **/

/**
 * SLA Countdown Widget — Enhanced Helpdesk
 *
 * Uses Luxon DateTime (Odoo passes record.data values as Luxon objects).
 * Ticks every second. Shows: status badge, remaining time, SLA target.
 */

import { Component, useState, onMounted, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const { DateTime } = luxon;

export class SlaCountdownWidget extends Component {
    static template = "enhanced_helpdesk.SlaCountdownWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            // badge
            icon: "⬜",
            statusLabel: "No SLA Set",
            cssClass: "sla-no-sla",
            // countdown
            remaining: "",
            // progress
            progressPercent: 0,
            progressBarClass: "bg-secondary",
            // target
            targetHours: null,
            targetDisplay: "",
            // meta
            hasDeadline: false,
        });
        this._timer = null;

        onMounted(() => {
            this._refresh();
            this._timer = setInterval(() => this._refresh(), 1000);
        });
        onWillUpdateProps(() => this._refresh());
        onWillUnmount(() => {
            if (this._timer) { clearInterval(this._timer); this._timer = null; }
        });
    }

    // ── Main refresh ──────────────────────────────────────────────────────────

    _refresh() {
        const { record, name } = this.props;
        const deadline    = record.data[name];           // Luxon DateTime | false
        const isOnHold    = Boolean(record.data.is_on_hold);
        const slaBreached = Boolean(record.data.sla_breached);
        const slaStatus   = record.data.sla_status || "";
        const holdHours   = record.data.total_hold_time_hours || 0;

        // SLA target (first SLA policy time in hours)
        const slaIds = record.data.sla_ids;
        let targetHours = null;
        let targetDisplay = "";
        if (slaIds && slaIds.records && slaIds.records.length) {
            const t = slaIds.records[0].data.time;
            if (t) {
                targetHours = t;
                targetDisplay = this._fmtHours(t);
            }
        }

        // ── No deadline ──────────────────────────────────────────────────────
        if (!deadline || !deadline.isValid) {
            Object.assign(this.state, {
                icon: "⬜", statusLabel: "No SLA Set", cssClass: "sla-no-sla",
                remaining: "—", progressPercent: 0, progressBarClass: "bg-secondary",
                targetHours, targetDisplay, hasDeadline: false,
            });
            return;
        }

        // ── Paused ───────────────────────────────────────────────────────────
        if (isOnHold || slaStatus === "paused") {
            Object.assign(this.state, {
                icon: "⏸", statusLabel: "Paused", cssClass: "sla-paused",
                remaining: "Timer paused", progressPercent: 50, progressBarClass: "bg-secondary",
                targetHours, targetDisplay, hasDeadline: true,
            });
            return;
        }

        // Adjust deadline for accumulated hold time
        const adjustedDeadline = deadline.plus({ hours: holdHours });
        const now = DateTime.local();
        const diffSeconds = Math.floor(adjustedDeadline.diff(now, "seconds").seconds);

        // ── Breached ─────────────────────────────────────────────────────────
        if (slaBreached || diffSeconds <= 0) {
            Object.assign(this.state, {
                icon: "🔴", statusLabel: "Breached", cssClass: "sla-breached",
                remaining: this._fmt(Math.abs(diffSeconds)) + " over deadline",
                progressPercent: 0, progressBarClass: "bg-danger",
                targetHours, targetDisplay, hasDeadline: true,
            });
            return;
        }

        // ── Active ───────────────────────────────────────────────────────────
        const hours = diffSeconds / 3600;
        let cssClass, icon, statusLabel, progressBarClass;

        if (hours > 24) {
            icon = "��"; statusLabel = "On Track";    cssClass = "sla-safe";     progressBarClass = "bg-success";
        } else if (hours > 2) {
            icon = "🟡"; statusLabel = "At Risk";     cssClass = "sla-warning";  progressBarClass = "bg-warning";
        } else {
            icon = "🔴"; statusLabel = "Near Breach"; cssClass = "sla-critical"; progressBarClass = "bg-danger";
        }

        // Progress relative to SLA target; fallback to 72 h window
        const window = targetHours || 72;
        const progressPercent = Math.min(100, Math.max(1, Math.round((hours / window) * 100)));

        Object.assign(this.state, {
            icon, statusLabel, cssClass,
            remaining: this._fmt(diffSeconds),
            progressPercent, progressBarClass,
            targetHours, targetDisplay, hasDeadline: true,
        });
    }

    // ── Formatters ────────────────────────────────────────────────────────────

    /** "2d 3h 14m 07s" */
    _fmt(totalSeconds) {
        if (totalSeconds <= 0) return "0s";
        const d = Math.floor(totalSeconds / 86400);
        const h = Math.floor((totalSeconds % 86400) / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = totalSeconds % 60;
        const parts = [];
        if (d > 0) parts.push(`${d}d`);
        if (h > 0) parts.push(`${h}h`);
        if (d === 0) parts.push(`${m}m`);
        if (d === 0 && h < 1) parts.push(`${String(s).padStart(2, "0")}s`);
        return parts.join(" ") || "0s";
    }

    /** float hours → "4h" or "1d 8h" */
    _fmtHours(h) {
        const d = Math.floor(h / 24);
        const rem = Math.round(h % 24);
        const parts = [];
        if (d > 0) parts.push(`${d}d`);
        if (rem > 0) parts.push(`${rem}h`);
        return parts.join(" ") || "0h";
    }
}

registry.category("fields").add("sla_countdown", {
    component: SlaCountdownWidget,
    supportedTypes: ["datetime"],
});
