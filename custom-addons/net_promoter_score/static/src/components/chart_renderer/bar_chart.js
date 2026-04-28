/** @odoo-module */

import { loadJS } from "@web/core/assets";

const { Component, onWillStart, useRef, onMounted } = owl;

export class ChartRenderer extends Component {
    setup() {
        this.chartRef = useRef("chart");

        onWillStart(async () => {
            await loadJS("/net_promoter_score/static/src/lib/chart.umd.min.js");
        });

        onMounted(() => this.renderChart());
    }

   renderChart(){
    const chartData = this.props.chartData;
    if (!chartData || !chartData.labels) return;

    new Chart(this.chartRef.el, {
        type: "bar",
        data: chartData,
        options: {
            responsive: true,
            plugins: {
                legend: { position: "bottom" },
                title: {
                    display: true,
                    text: this.props.title || "Monthly NPS Responses",
                    position: "top",
                },
            },
        },
    });
}

}

ChartRenderer.template = "net_promoter_score.ChartRenderer";
