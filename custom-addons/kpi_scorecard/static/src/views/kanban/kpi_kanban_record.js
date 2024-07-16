/** @odoo-module **/

import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { KANBAN_BOX_ATTRIBUTE } from "@web/views/kanban/kanban_arch_parser";
const { xml } = owl;


export class KpiKanbanRecord extends KanbanRecord {
    /*
    * Re-write to add its own classes for selected kanban record
    */
    getRecordClasses() {
        let result = super.getRecordClasses();
        const attrClass = this.props.record._getActionsClass();
        return result + attrClass + " kpi-kanban-article";
    }
    /*
    * The method to manage clicks on kanban record
    */
    onGlobalClick(ev) {
        if (ev.target.closest(".kpi-edit-target")) { this.props.record._onEditTarget(ev) }
        else if (ev.target.closest(".kpi-show-history")) { this.props.record._onShowHistory(ev) }           
        else if (ev.target.closest(".kpi-remove-target")) { this.props.record._onRemoveTarget(ev) }
        else { this.props.record._onEditTarget(ev) }
    }
};

KpiKanbanRecord.template = xml`
    <div
        role="article"
        t-att-class="getRecordClasses()"
        t-on-click.synthetic="onGlobalClick"
        t-ref="root">
        <t t-call="{{ templates['${KANBAN_BOX_ATTRIBUTE}'] }}"/>
    </div>`;
