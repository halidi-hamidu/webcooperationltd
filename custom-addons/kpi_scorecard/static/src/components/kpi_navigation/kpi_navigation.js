/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { Domain } from "@web/core/domain";
import { loadCSS, loadJS } from "@web/core/assets";
import { KpiJsTreeContainer } from "@kpi_scorecard/components/jstree_container/jstree_container";
import { KpiPeriods } from "@kpi_scorecard/components/kpi_periods/kpi_periods";
const { Component, onWillStart } = owl;

const searchSections = { "kpi_kanban_categories": _lt("Categories"), "kpi_tags": _lt("Tags") }


export class KpiNavigation extends Component {
    /*
    * Re-write to import required services and update props on the component start
    */
    setup() {
        this.jsTreeDomain = [];
        this.jsTreeDomains = {};
        onWillStart(async () => {
            const proms = [
                loadJS("/kpi_scorecard/static/lib/jstree/jstree.min.js"),
                loadCSS("/kpi_scorecard/static/lib/jstree/themes/default/style.css"),
            ]
            return Promise.all(proms);
        });
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
    * The method to prepare jstreecontainer props
    */
    getKpiPeriodProps(key) {
        return {
            onUpdateSearch: this.onUpdateSearch.bind(this),
            kanbanModel: this.props.kanbanModel,
        }
    }
    /*
    * The method to prepare the domain by all JScontainers and KPI Periods and notify searchmodel
    */
    onUpdateSearch(jstreeId, domain) {
        const jsTreeDomain = this._prepareJsTreeDomain(jstreeId, domain);
        if (this.jsTreeDomain != jsTreeDomain) {
            this.jsTreeDomain = jsTreeDomain;
            this.env.searchModel.toggleJSTreeDomain(this.jsTreeDomain);
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
};

KpiNavigation.template = "kpi_scorecard.KpiNavigation";
KpiNavigation.components = { KpiJsTreeContainer, KpiPeriods }
