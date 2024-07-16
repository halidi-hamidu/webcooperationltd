/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { Domain } from "@web/core/domain";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { useService } from "@web/core/utils/hooks";
const { Component, onMounted, onWillStart, useState } = owl;

const componentModel = "kpi.period";


export class KpiPeriods extends Component {
    /*
    * Re-write to import required services and update props on the component start
    */
    setup() {
        this.state = useState({ 
            periodIds: null,
            thisPeriodId: null,
        });
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
        onWillStart(async () => {
            await this._loadPeriods();
        });
        onMounted(() => {
            this._notifyPeriodChange(true);
        })
    }
    /*
    * The method to load periods data and define the initial current period
    */
    async _loadPeriods(toSetNewPeriodId) {
        var periodIds = await this.orm.call(
            componentModel,
            "action_return_periods",
            [toSetNewPeriodId ? toSetNewPeriodId.id : null],
        );
        var thisPeriodId = false;
        if (periodIds.length == 0) { periodIds = null }
        else if (toSetNewPeriodId) { thisPeriodId = this._getThisPeriodDict(periodIds.filter(period => period.id ==  toSetNewPeriodId.id)) }
        else { thisPeriodId = this._getThisPeriodDict(periodIds.filter(period => period.selected ==  true)) }
        Object.assign(this.state, { periodIds: periodIds, thisPeriodId: thisPeriodId });
    }
    /*
    * The method to notify the search model that the period is changed
    * IMPORTANT: onUpdateDomain might trigger kanban model notify but migth also not, so we have to refresh it manually
    */
    async _notifyPeriodChange(searchNotify) {
        this.props.kanbanModel.kpiPeriod = this.thisPeriodId;
        var modelNotifyNeeded = false;
        if (searchNotify) {
            const thisPeriodId = this.thisPeriodId ? this.thisPeriodId.id : false;
            modelNotifyNeeded = await this.props.onUpdateSearch("kpi_periods", [["period_id", "=", thisPeriodId]]);
        };
        if (!modelNotifyNeeded) { this.refreshAfterUpdate() };
    }
    /*
    * Getter for thisPeriodId
    */
    get thisPeriodId() {
        return this.state.thisPeriodId;
    }
    /*
    * The method to select a new KPI period
    */
    _onChangePeriod(event) {
        var thisPeriodId = false;
        if (this.state.periodIds && event.currentTarget.value) {
            const selectedPeriodId = parseInt(event.currentTarget.value);
            thisPeriodId = this._getThisPeriodDict(this.state.periodIds.filter(period => period.id == selectedPeriodId));
        };
        Object.assign(this.state, { thisPeriodId: thisPeriodId });
        this._notifyPeriodChange(true);
    }
    /*
    * The method to trigger a period close
    */
    async _onClosePeriod() {
        if (this.thisPeriodId && this.thisPeriodId.state == "open") {
            await this.orm.call(
                componentModel,
                "action_close",
                [[this.thisPeriodId.id]],
            );
            this._updateThisPeriodState("closed");
        };
    }
    /*
    * The method to trigger a period reopening
    */
    async _onOpenPeriod() {
        if (this.thisPeriodId && this.thisPeriodId.state == "closed") {
            await this.orm.call(
                componentModel,
                "action_reopen",
                [[this.thisPeriodId.id]],
            );
            this._updateThisPeriodState("open");
        }
    }
    /*
    * The method to trigger a dialog to create a new period
    */
    async _onNewPeriod() {
        this.dialogService.add(FormViewDialog, {
            resModel: componentModel,
            title: _lt("New KPI Period"),
            context: { "quick_kpi_period": true },
            onRecordSaved: async (formRecord) => { 
                await this._loadPeriods({ "id": formRecord.data.id, "state": formRecord.data.state});
                await this._notifyPeriodChange(true);
                await this._onCalculatePeriodKpis();
            },
        });
    }
    /*
    * The method to trigger this period KPIs update
    */
    async _onCalculatePeriodKpis() {
        if (this.thisPeriodId && this.thisPeriodId.state == "open") {
            await this.orm.call(componentModel, "action_calculate_kpis", [[this.thisPeriodId.id]]);
            await this.refreshAfterUpdate();
        };
    }
    /*
    * The method to load updated records after update (IMPORTANT: no changes to period and search domain)
    */
    async refreshAfterUpdate() {
        await this.props.kanbanModel.root.load();
        this.props.kanbanModel.notify();
    } 
    /*
    * The method to update thisPeriodId and thisPeriodId based on orm call for periods change/create
    */
    _updateThisPeriodState(state) {
        this.thisPeriodId.state = state;
        const thisPeriods = this.state.periodIds.filter(period => period.id == this.thisPeriodId.id);
        if (thisPeriods.length != 0) { thisPeriods[0].state = state };
        this._notifyPeriodChange();
    }
    /*
    * The method to prepare thisPeriod dict based on found periods
    */
    _getThisPeriodDict(properPeriods) {
        if (properPeriods.length != 0) {
            return { 
                "id": properPeriods[0].id, 
                "state": properPeriods[0].state, 
                "length": properPeriods[0].length,
                "companyId": properPeriods[0].company_id,
            }
        };
        return false;
    }
};

KpiPeriods.template = "kpi_scorecard.KpiPeriods";
