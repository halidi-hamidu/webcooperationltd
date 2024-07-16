/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { Component, onWillStart, useState } from "@odoo/owl";
import { KpiChart } from "@kpi_scorecard/components/kpi_chart/kpi_chart";
import { useService } from "@web/core/utils/hooks";

const componentModel = "kpi.item";


export class KpiHistoryDialog extends Component {
    /*
    * Re-write to trigger services and hooks
    */
    setup() {
        this.state = useState({ fullHistory: null });
        this.orm = useService("orm");
        onWillStart(async () => {
            await this.loadFullHistory(this.props);
        });
    }
    /*
    * The method to save history to the state
    */
    async loadFullHistory(props) {
        var fullHistory = await this.orm.call(
            componentModel, 
            "action_get_full_history", 
            [[props.kpiId], props.kpiPeriodCompanyId]
        );
        if (fullHistory.length == 0) { fullHistory = null };
        Object.assign(this.state, { fullHistory: fullHistory });
    }
}

KpiHistoryDialog.template = "kpi_scorecard.KpiHistoryDialog";
KpiHistoryDialog.components = { Dialog, KpiChart };
KpiHistoryDialog.props = {
    close: Function,
    kpiId: { type: Number, optional: false },
    kpiPeriodLength: { type: Number, optional: false},
    kpiPeriodCompanyId: { type: Number, optional: false},
    title: { type: String, optional: true },
};
