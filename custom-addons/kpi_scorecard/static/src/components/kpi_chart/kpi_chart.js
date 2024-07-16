/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { loadJS } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";
const { Component, onMounted, onWillStart, onWillUpdateProps, onPatched, useState } = owl;

const componentModel = "kpi.item";


export class KpiChart extends Component {
    /*
    * Re-write to import required services and update props on the component start
    */
    setup() {
        this.state = useState({ 
            kpiChartType: this.props.kpiChartType, 
            showTargets: this.props.showTargets,
            showActual: this.props.showActual, 
            kpiTitle: "", 
            kpiOrder: true, 
            chartData: null,
        });
        this.orm = useService("orm");
        this.barsDataSet = []; this.barsDataSetActual = []; this.barsDataSetTargets = [];
        this.lineDataSet = []; this.lineDataSetActual = []; this.lineDataSetTargets = []; 
        this.requireUpdate = false; this.changedChartType = false; this.activatedChart = false;
        onWillStart(async () => {
            const proms = [
                loadJS("/web/static/lib/Chart/Chart.js"),
                this._loadKpiSettings(this.props),
                this._loadKpiHistory(this.props),
            ]
            return Promise.all(proms);
        });
        onWillUpdateProps(async(nextProps) => {
            if (nextProps.kpiPeriodLength != this.props.kpiPeriodLength || nextProps.kpiPeriodCompanyId != this.props.kpiPeriodCompanyId) {
                this.requireUpdate = true;
                await this._loadKpiHistory(nextProps);
            }
            else {
                if (
                    nextProps.kpiChartType != this.props.kpiChartType || nextProps.showTargets != this.props.showTargets 
                    || nextProps.showActual != this.props.showActual
                ) {
                    this.changedChartType = true 
                };                          
            };
        })
        onMounted(async () => {
            this._activateChart();
            this._updateChart();

        });
        onPatched(() => {
            if (!this.activatedChart) {
                this._activateChart();
            };
            if (this.requireUpdate) { this._updateChart() };
            if (this.changedChartType) { this._onToggleChartType(this.props.kpiChartType) }
        })
    }
    /*
    * The method to get kpi.scorecard.line for this KPI based on props
    */
    async _loadKpiHistory(props) {
        var chartData = await this.orm.call(
            componentModel, 
            "action_get_history", 
            [[props.kpiId], props.kpiPeriodLength, props.kpiPeriodCompanyId.id]
        );
        if (chartData.length == 0) { chartData = null };
        Object.assign(this.state, { chartData: chartData }); 
    }
    /*
    * The method to get KPI properties
    */
    async _loadKpiSettings(props) {
        const kpiSettingsDict = await this.orm.read(componentModel, [props.kpiId], ["name", "result_type"]);
        Object.assign(this.state, { 
            kpiTitle: kpiSettingsDict[0].name,
            kpiOrder: kpiSettingsDict[0].result_type == "more",
        });
    }
    /*
    * The method to active shart and required elements
    */
    _activateChart() {
        if (!this.state.chartData) { return };
        if (this.activatedChart) { return };
        const kpiCanvas = $(".kpi-chart-canvas#kpi_canvas_" + this.props.kpiId);
        if (kpiCanvas.length != 0) {
            this.kpiChart = new Chart(kpiCanvas[0].getContext("2d"), {type: "line", data: {}});
            this.kpiContainer = $(".kpi-chart#kpi_chart_" + this.props.kpiId);
        };
        this.activatedChart = true;
    }
    /*
    * The method to update chart for data
    */
    _updateChart() {
        if (!this.state.chartData) { return }
        // to get to the navigatop settings
        Object.assign(this.state, { 
            kpiChartType: this.props.kpiChartType, 
            showTargets: this.props.showTargets,
            showActual: this.props.showActual,
        });
        var data = [], labels = [], backgroud_colors = [], target_data = [];
        var barsDataSet = []; var lineDataSet = [];
        this.state.chartData.forEach(function (kpiLine) {
            labels.push(kpiLine.date);
            data.push(kpiLine.value);
            target_data.push(kpiLine.target_value);
            backgroud_colors.push(kpiLine.background);
        });
        // bar data sets
        const barsDataSetActual = {
            data: data,
            fill: "start",
            label: _lt("Actual"),
            backgroundColor: backgroud_colors,                   
        };
        const barsDataSetTargets = {
            data: target_data,
            fill: "start",
            label: _lt("Target"),
            backgroundColor: "#0180a5",                   
        };
        if (this.state.showActual) { barsDataSet.push(barsDataSetActual) };
        if (this.state.showTargets) { barsDataSet.push(barsDataSetTargets) };
        // line data sets
        const lineDataSetActual = {
            data: data,
            fill: "start",
            label: _lt("Actual"),
            backgroundColor: "#0180a5",                
        };
        const lineDataSetTargets = {
            data: target_data,
            fill: "start",
            label: _lt("Target"),
            backgroundColor: "#0180a5",                    
        };     
        // have to check everything again, since colors differ for different options
        if (this.state.kpiOrder) {
            if (this.state.showActual) {
                lineDataSet.push({
                    data: data,
                    fill: "start",
                    label: _lt("Actual"),
                    backgroundColor: "rgb(0, 136, 24, 0.7)" ,
                })
            }
            if (this.state.showTargets) {
                lineDataSet.push({
                    data: target_data,
                    fill: "start",
                    label: _lt("Target"),
                    backgroundColor: "rgb(210, 63, 58)",                      
                })
            }
        }
        else {
            if (this.state.showActual) {
                lineDataSet.push({
                    data: target_data,
                    fill: "start",
                    label: _lt("Target"),
                    backgroundColor: "rgb(0, 136, 24, 0.7)",
                },)
            }
            if (this.state.showTargets) {
                lineDataSet.push({
                    data: data,
                    fill: "start",
                    label: _lt("Actual"),
                    backgroundColor: "rgb(210, 63, 58)", 
                })
            }
        };
        // save for further use        
        this.barsDataSet = barsDataSet;
        this.barsDataSetActual = [barsDataSetActual];
        this.barsDataSetTargets = [barsDataSetTargets];
        this.lineDataSet = lineDataSet;
        this.lineDataSetActual = [lineDataSetActual];
        this.lineDataSetTargets = [lineDataSetTargets];        
        // update chart
        this.kpiChart.type = this.state.kpiChartType;
        this.kpiChart.options = { 
            maintainAspectRatio: false,
            responsive: true,
            xAxes: [{ offset: this.state.kpiChartType == "bar" ? true : false }],
        };
        this.kpiChart.config.type = this.state.kpiChartType;
        this.kpiChart.data = { 
            labels: labels, 
            datasets: this._getChartData(), 
        };
        this.kpiChart.update();
        this.requireUpdate = false; this.changedChartType = false; 
    }
    /*
    * The method to change the chart type
    */
    _onToggleChartType(chartType) {
        if (!this.state.chartData) { return }
        if (
            this.state.kpiChartType != chartType || this.state.showTargets != this.props.showTargets 
            || this.state.showActual != this.props.showActual
        ) {
            Object.assign(this.state, { 
                kpiChartType: chartType,
                showTargets: this.props.showTargets,
                showActual: this.props.showActual,
            });
            this.kpiChart.config.type = chartType;
            this.kpiChart.data.datasets = this._getChartData();
            this.kpiChart.options.scales = { xAxes: [{ offset: chartType == "bar" ? true : false }] }
            this.kpiChart.update();
        };
        this.changedChartType = false;
    }
    /*
    * The method to define which data to use
    */
    _getChartData() {
        if (this.state.kpiChartType == "line") {
            if (this.state.showActual && !this.state.showTargets) {
                return this.lineDataSetActual;
            }
            else if (!this.state.showActual && this.state.showTargets) {
                return this.lineDataSetTargets;
            };
            return this.lineDataSet;
        }
        else if (this.state.kpiChartType == "bar") {
            if (this.state.showActual && !this.state.showTargets) {
                return this.barsDataSetActual;
            }
            else if (!this.state.showActual && this.state.showTargets) {
                return this.barsDataSetTargets;
            };
            return this.barsDataSet;
        };
        return [];
    }
    /*
     * The method to open a chart to the full view
     */
    _onClickExpandChart() {
        if (this.kpiContainer.hasClass("kpi-chart-full-screen")) {
            this.kpiContainer.removeClass("kpi-chart-full-screen");
        }
        else { this.kpiContainer.addClass("kpi-chart-full-screen") };
        this.kpiChart.resize();
    }
    /*
    * The method to catch Escape event and close the full view
    */
    async onInputKeydown(ev) {
        if (event.key === "Escape" && this.kpiContainer.hasClass("kpi-chart-full-screen")) {
            this._onClickExpandChart();
        };
    }
};

KpiChart.template = "kpi_scorecard.KpiChart";
