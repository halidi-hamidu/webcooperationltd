/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KpiKanbanController } from "./kpi_kanban_controller";
import { KpiKanbanModel } from "./kpi_kanban_model";
import { KpiKanbanRenderer } from "./kpi_kanban_renderer";
import { KpiSearchModel } from "../search/kpi_search_model";


export const KpiKanbanView = Object.assign({}, kanbanView, {
    SearchModel: KpiSearchModel,
    Controller: KpiKanbanController,
    Model: KpiKanbanModel,
    Renderer: KpiKanbanRenderer,
    searchMenuTypes: ["filter", "favorite"],
    buttonTemplate: "kpi_scorecard.KpiKanbanViewButtons",
});

registry.category("views").add("kpi_kanban", KpiKanbanView);
