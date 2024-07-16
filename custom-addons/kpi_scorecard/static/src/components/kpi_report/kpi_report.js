/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { Domain } from "@web/core/domain";
import { KpiChart } from "@kpi_scorecard/components/kpi_chart/kpi_chart";
import { KpiJsTreeContainer } from "@kpi_scorecard/components/jstree_container/jstree_container";
import { loadCSS, loadJS } from "@web/core/assets";
import { registry } from '@web/core/registry';
import { useService } from "@web/core/utils/hooks";
const { Component, onMounted, onWillStart, onWillUpdateProps, useState } = owl;

const componentModel = "kpi.item";
const searchSections = { 
    "kpi_kanban_categories": _lt("Categories"),
    "kpi_items": _lt("KPIs"),
    "kpi_tags": _lt("Tags"),
}


export class KpiReport extends Component {
    /*
    * Re-write to import required services and update props on the component start
    */
    setup() {
        this.jsTreeDomain = [];
        this.jsTreeDomains = {};
        this.state = useState({ 
            kpiChartType: "line",
            showTargets: true,
            showActual: true,
            kpiSet: null,
            periodIds: null,
            thisPeriodId: null,
            kpiCompanies: null,
            thisCompanyId: null,
            multiCompany: null,
        });
        this.orm = useService("orm");
        this.userService = useService("user");
        onWillStart(async () => {
            await this._loadCompanies(); // beforehand since influence _loadAllKpis
            const proms = [
                loadJS("/kpi_scorecard/static/lib/jstree/jstree.min.js"),
                loadCSS("/kpi_scorecard/static/lib/jstree/themes/default/style.css"),
                this._loadAllKpis(),
                this._loadPeriods(),
            ]
            return Promise.all(proms);
        });
    }
    /*
    * The method to get all KPIs
    */
    async _loadAllKpis() {
        var kpiSet = await this.orm.searchRead(componentModel, this.jsTreeDomain, ["id"]);
        if (kpiSet.length == 0) { kpiSet = null };
        Object.assign(this.state, { kpiSet: kpiSet });
    }
    /*
    * The method to get period types
    */
    async _loadPeriods() {
        var periodIds = await this.orm.call("kpi.period", "action_return_period_types", []);
        var thisPeriodId = false;
        if (periodIds.length == 0) { periodIds = [] };
        periodIds.push({ "length": -1, "name": _lt("All Period Types")}); 
        thisPeriodId = periodIds[0];
        Object.assign(this.state, { periodIds: periodIds, thisPeriodId: thisPeriodId });
    }
    /*
    * The method to load companies' list (for multi-company environment)
    */
    async _loadCompanies() {
        const multiCompany = await this.userService.hasGroup("base.group_multi_company");
        var kpiCompanies = await this.orm.call("kpi.period", "action_get_companies", []);
        var thisCompanyId = false;
        if (kpiCompanies.length == 0) { kpiCompanies = null }
        else { 
            const thisCompanies = kpiCompanies.filter(period => period.selected ==  true)
            if (thisCompanies.length != 0) { thisCompanyId = thisCompanies[0] }
        };
        // so, KPIs are immediately taken only for the chosen company
        this.jsTreeDomain = this._prepareJsTreeDomain("companies", this._prepareCompanyDomain(thisCompanyId)).toList();
        Object.assign(this.state, { kpiCompanies: kpiCompanies, thisCompanyId: thisCompanyId, multiCompany: multiCompany});
    }
    /*
    * The method to prepare jstreecontainer props
    */
    getJsTreeProps(key) {
        return {
            jstreeTitle: searchSections[key],
            jstreeId: key,
            onUpdateSearch: this.onUpdateSearch.bind(this)
        }
    }
    /*
    * The method to select a new KPI period type
    */
    _onChangePeriod(event) {
        var thisPeriodId = false;
        if (this.state.periodIds && event.currentTarget.value) {
            const selectedPeriodId = parseInt(event.currentTarget.value);
            const thisPeriodIds = this.state.periodIds.filter(period => period.length == selectedPeriodId);
            if (thisPeriodIds.length != 0) { thisPeriodId = thisPeriodIds[0] } 
        };
        Object.assign(this.state, { thisPeriodId: thisPeriodId });
    }
    /*
    * The method to select a new Company
    */
    _onChangeCompany(event) {
        var thisCompanyId = false;
        if (this.state.kpiCompanies && event.currentTarget.value) {
            const selectedCompany = parseInt(event.currentTarget.value);
            const thisCompanies = this.state.kpiCompanies.filter(comp => comp.id == selectedCompany);
            if (thisCompanies.length != 0) { thisCompanyId = thisCompanies[0] } 
        };
        Object.assign(this.state, { thisCompanyId: thisCompanyId });
        // so, KPIs list will also not include other company's KPIs
        this.onUpdateSearch("companies", this._prepareCompanyDomain(thisCompanyId));
    }
    /*
    * The method to choose overall graph type
    */
    _onChangeGraphType(event) {
        Object.assign(this.state, { kpiChartType: event.currentTarget.value });
    }
    /*
    * The method to change chart data to targets
    */
    _onToggleTargets(event) {
        Object.assign(this.state, { showTargets: event.currentTarget.checked });
    }
    /*
    * The method to change chart data to actual
    */
    _onToggleActual(event) {
        Object.assign(this.state, { showActual: event.currentTarget.checked });
    }
    /*
    * The method to show proper records based on selected filters
    */
    onUpdateSearch(jstreeId, domain) {
        const jsTreeDomain = this._prepareJsTreeDomain(jstreeId, domain).toList();
        if (this.jsTreeDomain != jsTreeDomain) {
            this.jsTreeDomain = jsTreeDomain;
            this._loadAllKpis();
            return true;
        };
        return false;
    }
    /*
    * The method to prepare domain based on all jstree components
    */
    _prepareJsTreeDomain(jstreeId, domain) {
        var jsTreeDomain = [];
        this.jsTreeDomains[jstreeId] = domain;
        _.each(Object.values(this.jsTreeDomains), function (val_domain) {
            jsTreeDomain = Domain.and([jsTreeDomain, val_domain])
        });
        return jsTreeDomain
    }
    /*
    * The method to get company domain based on the chosen company
    */
    _prepareCompanyDomain(thisCompanyId) {
        return Domain.or([[["company_id", "=", false]], [["company_id", "=", thisCompanyId.id]]]).toList()
    }
}

KpiReport.template = "kpi_scorecard.KpiReport";
KpiReport.components = { KpiChart, KpiJsTreeContainer }

registry.category("actions").add("kpi.scorecard.report", KpiReport);
