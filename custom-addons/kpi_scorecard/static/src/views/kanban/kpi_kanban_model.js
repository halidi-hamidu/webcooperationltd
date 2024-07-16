/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { KanbanModel } from "@web/views/kanban/kanban_model";
import { KpiHistoryDialog } from "@kpi_scorecard/views/dialogs/kpi_history_dialog/kpi_history_dialog";
import { useService } from "@web/core/utils/hooks";
const { onWillStart } = owl;

const componentModel = "kpi.scorecard.line";


export class KpiKanbanModel extends KanbanModel {
    /*
    * Re-write to introduce own kpet settings
    */
    setup(params) {
        this.kpiPeriod = false; // applied at kpi_period_navigation
        this.userService = useService("user");
        this.actionService = useService("action");
        this.dialogService = useService("dialog");
        onWillStart(async () => {
            this.kpiAdmin = await this.userService.hasGroup("kpi_scorecard.group_kpi_admin");
        });
        super.setup(...arguments);
    }
    /*
    * The method to make sure the period is for action is opened
    */
    _checkPeriodOpened() {
        return this.kpiPeriod && this.kpiPeriod.state == "open";
    }
    /*
    * The method to substitute current KPI targets with the targets from another period
    */
    async _onOpenReplaceTargets() {
        if (this._checkPeriodOpened()) {
            const options = {
                additionalContext: { "default_period_id":  this.kpiPeriod.id },
                onClose: async () => {
                    await this.root.load();
                    this.notify();
                },
            };
            await this.actionService.doAction("kpi_scorecard.kpi_copy_template_action", options);
        };      
    }
    /*
    * The method to get the Excel table of the current period KPI targets
    */
    async _onExportScorecard() {
        if (this.kpiPeriod) {
            const actioDict = await this.orm.call("kpi.period", "action_export_scorecard", [[ this.kpiPeriod.id ]]);
            await this.actionService.doAction(actioDict);
        }
    }
    /*
    * The method to open a target form for existing KPI target or for a newly created one
    */
    async _onOpenTarget(resId) {
        if (this._checkPeriodOpened()) {
            this.dialogService.add(FormViewDialog, {
                resModel: componentModel,
                title: _lt("Update Target"),
                resId: resId,
                context: {"default_period_id": this.kpiPeriod.id},
                onRecordSaved: async (formRecord) => { 
                    await this.root.load();
                    this.notify();
                },
            });
        };        
    }
    /*
    * The method to open a target form for existing KPI target or for a newly created one
    */
    async _onRemoveTarget(resId) {
        if (this._checkPeriodOpened()) {
            if (! confirm(_lt("Do you really want to delete this KPI target?"))){ return false };
            await this.orm.call(componentModel, "unlink", [[ resId ]]);
            await this.root.load();
            this.notify();
        };      
    }
    /*
    * The method to open the dialog with history
    */
    async _onShowHistory(thisKpiId) {
        if (this.kpiPeriod) {
            this.dialogService.add(KpiHistoryDialog, {
                title: _lt("KPI History"),
                kpiId: thisKpiId,
                kpiPeriodLength: this.kpiPeriod.length, 
                kpiPeriodCompanyId: this.kpiPeriod.companyId,
            });
        }
    }
};

export class KpiKanbanRecord extends KanbanModel.Record {
    /*
    * The method to prepare the class based on the current model state
    */
    _getActionsClass() {
        var stateClass = "";
        if (!this.model.kpiPeriod) { stateClass += " kpi-kanban-attr-no-period " }
        else if (this.model.kpiPeriod.state == "closed") { stateClass += " kpi-kanban-attr-no-open-period " };
        if (this.paddingLevel) { stateClass += " kpi-kanban-left-"+this.paddingLevel + " " };
        return stateClass
    }
    /*
    * The method to open the KPI target in dialog for editing
    */
    async _onEditTarget(ev) {
        if (this.data.edit_rights) { this.model._onOpenTarget(this.resId) }
    }
    /*
     * The method to remove KPI target
    */
    async _onRemoveTarget(ev) {
        if (this.data.edit_rights) { this.model._onRemoveTarget(this.resId) };
    }
    /*
    * The method to show history dialog for the target
    */
    _onShowHistory(ev) {
        this.model._onShowHistory(this.data.kpi_id[0]);
    }
};

KpiKanbanModel.Record = KpiKanbanRecord;
