/** @odoo-module **/

import { KanbanController } from "@web/views/kanban/kanban_controller";

export class KpiKanbanController extends KanbanController {
    /*
    * Re-write to introduce own create action and dialog ()
    */
    async createRecord() {
        this.model._onOpenTarget(false);
    }
    /*
    * The method to copy targets from another period
    */
    async onSubstituteTargets() {
        if (this.kpiAdmin) { this.model._onOpenReplaceTargets() }
    }
    /*
    * The method to export this period KPI targets to the xlsx table
    */
    async onExportScorecard() {
        this.model._onExportScorecard();
    }
    /*
    * Getter method for KPI period (kept in model)
    */
    get kpiPeriod() {
        return this.model.kpiPeriod;
    }
    /*
    * Getter method for whether user is a KPI admin (kept in model)
    */
    get kpiAdmin() {
        return this.model.kpiAdmin;
    }
};

KpiKanbanController.template = "kpi_scorecard.KpiKanbanView";
