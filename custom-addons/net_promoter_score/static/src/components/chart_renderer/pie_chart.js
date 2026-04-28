/** @odoo-module */
import {loadJS } from '@web/core/assets';

const { Component, onWillStart, useRef, onMounted } = owl;

export class RenderPieChart  extends Component{
    setup(){
        this.chartRef = useRef("pie_chart");
        onWillStart(async () => {
            await loadJS("/net_promoter_score/static/src/lib/chart.umd.min.js");
        });
        onMounted(() => this.renderPieChart());
    }

renderPieChart() {

    const chartData = this.props.chartData;
    new Chart(this.chartRef.el, {
        type: "pie",
        data: {
            labels: ["Promoters", "Detractors", "Passives"],
            datasets: [
                {
                    data: chartData,
                    backgroundColor: [
                        "rgba(75, 192, 192, 0.6)",   // Promoters
                        "rgba(255, 99, 132, 0.6)",   // Detractors
                        "rgba(255, 206, 86, 0.6)",   // Passives
                    ],
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: "bottom",
                },
                title: {
                    display: true,
                    text: "Monthly NPS Responses",
                    position: "top",
                },
            },
        },
    });
}

}
RenderPieChart.template = "net_promoter_score.pieChartRenderer";