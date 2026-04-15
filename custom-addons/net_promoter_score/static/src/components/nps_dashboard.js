/** @odoo-module */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { NpsMetric } from "./cards/metric_card";
import { Voters } from "./tables/voters";
import { ChartRenderer } from "./chart_renderer/bar_chart";
import { RenderPieChart } from "./chart_renderer/pie_chart";

const { Component, onWillStart, useState } = owl;

export class OwlNpsDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({
            npsData: {
                company_nps: 0,
                total_responses: 0,
                promoters: 0,
                detractors: 0,
                passives: 0,
                chartData: [],
                nps_status: "",
            },
        });

        onWillStart(async () => {
            await this.loadNpsData();
        });
    }


    async loadNpsData() {
        const records = await this.orm.searchRead("net.promoter.score", [], [
            "score",
            "voter_identification",
            "create_date"
        ]);

        const promoters = records.filter(r => r.voter_identification === "Promoter").length;
        const detractors = records.filter(r => r.voter_identification === "Detractor").length;
        const passives = records.filter(r => r.voter_identification === "Passive").length;

        const total = records.length;
        const company_nps = total ? ((promoters - detractors) / total) * 100 : 0;

        const promoter_percentage =  total ? (promoters / total) * 100 : 0;
        const detractor_percentage = total ? (detractors / total) * 100 : 0;

        // NPS = %PROMOTERS - %DETRACTORS
        const nps_score = promoter_percentage - detractor_percentage

       
        if (nps_score >= 50) {
            this.state.npsData.nps_status = "Excellent";
        } else if (nps_score >= 0) {
            this.state.npsData.nps_status = "Good";
        } else if (nps_score >= -50) {
            this.state.npsData.nps_status = "Needs Improvement";
        } else {
            this.state.npsData.nps_status = "Poor";
        }
         
        // Chart Data - Monthly
        const monthMap = Array.from({ length: 12 }, (_, i) => ({
            month: new Date(0, i).toLocaleString("en", { month: "short" }),
            Promoter: 0,
            Passive: 0,
            Detractor: 0,
        }));

        for (const rec of records) {
            const date = new Date(rec.create_date);
            const monthIndex = date.getMonth(); 
            const category = rec.voter_identification;

            if (["Promoter", "Passive", "Detractor"].includes(category)) {
                monthMap[monthIndex][category]++;
            }
        }

        const chartData = {
            labels: monthMap.map(e => e.month),
            datasets: [
                {
                    label: "Promoters",
                    data: monthMap.map(e => e.Promoter),
                    backgroundColor: "rgba(75, 192, 192, 0.6)",
                },
                {
                    label: "Passives",
                    data: monthMap.map(e => e.Passive),
                    backgroundColor: "rgba(255, 206, 86, 0.6)",
                },
                {
                    label: "Detractors",
                    data: monthMap.map(e => e.Detractor),
                    backgroundColor: "rgba(255, 99, 132, 0.6)",
                },
            ],
        };

        const pieChartData = [promoters, detractors, passives];
        this.state.npsData = {
            company_nps: company_nps.toFixed(2),
            total_responses: total,
            promoters: promoters,
            detractors: detractors,
            passives: passives,
            chartData: chartData,
            pieChartData: pieChartData,
            nps_score: nps_score.toFixed(2),
            nps_status :this.state.npsData.nps_status,

            
        };
    }


}

OwlNpsDashboard.template = "net_promoter_score.OwlNpsDashboard";
OwlNpsDashboard.components = { NpsMetric, ChartRenderer, Voters, RenderPieChart };

registry.category("actions").add("net_promoter_score.nps_dashboard_tags", OwlNpsDashboard);
