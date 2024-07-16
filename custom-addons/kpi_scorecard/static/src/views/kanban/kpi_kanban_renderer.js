/** @odoo-module **/

import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { KpiKanbanRecord } from "./kpi_kanban_record";
import { KpiNavigation } from "@kpi_scorecard/components/kpi_navigation/kpi_navigation";
const { onWillRender } = owl;


export class KpiKanbanRenderer extends KanbanRenderer {
    /*
    * Re-write to trigger hierarchy updated based on shown records
    */
    setup() {
        super.setup(...arguments);
        onWillRender(async () => { await this._reApplyHierarchy() })
    }
    /*
    * The method to find each shown record and calculate padding based on its shown parent
    */
    _reApplyHierarchy() {
        const allShownIds = this.props.list.records.map(function (el) { return el.resId.toString() });
        _.each(this.props.list.records, function (record) {
            if (record.data.all_parents) {
                const allRecordParents = record.data.all_parents.split(",");
                const shownRecordParents = allRecordParents.filter(resId => allShownIds.includes(resId));
                record.paddingLevel = shownRecordParents.length;
            }
        });
    }
    /*
    * The method to ProductNavigation (left navigation)
    */
    getKpiNavigationProps() {
        return { kanbanModel: this.props.list.model }
    }
};

KpiKanbanRenderer.template = "kpi_scorecard.KpiKanbanRenderer";
KpiKanbanRenderer.components = Object.assign({}, KanbanRenderer.components, {
    KpiNavigation,
    KanbanRecord: KpiKanbanRecord,
});
