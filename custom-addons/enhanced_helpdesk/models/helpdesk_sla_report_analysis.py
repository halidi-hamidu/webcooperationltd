from odoo import fields, models, tools


class HelpdeskSlaReportAnalysis(models.Model):
    _inherit = 'helpdesk.sla.report.analysis'

    sla_fail_count = fields.Integer(
        string="SLA Failures",
        aggregator="sum",
        readonly=True,
        help="Number of SLA statuses that failed"
    )
    sla_success_count = fields.Integer(
        string="SLA Successes",
        aggregator="sum",
        readonly=True,
        help="Number of SLA statuses that succeeded (reached before deadline)"
    )
    sla_total_count = fields.Integer(
        string="Total SLA Checks",
        aggregator="sum",
        readonly=True,
        help="Total number of SLA status entries (fail + success + ongoing)"
    )
    sla_fail_rate = fields.Float(
        string="SLA Failure Rate (%)",
        aggregator="avg",
        readonly=True,
        digits=(5, 1),
        help="Percentage of SLA statuses that failed out of all completed checks"
    )
    sla_success_rate = fields.Float(
        string="SLA Success Rate (%)",
        aggregator="avg",
        readonly=True,
        digits=(5, 1),
        help="Percentage of SLA statuses that succeeded out of all completed checks"
    )

    def _select(self):
        select_str = super()._select()
        # Append rate columns to the existing SELECT
        select_str = select_str.rstrip().rstrip(',')
        select_str += """,
            -- SLA counts per ticket row
            CASE WHEN (
                (SLA_S.reached_datetime IS NOT NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.reached_datetime >= SLA_S.deadline)
                OR (SLA_S.reached_datetime IS NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC')
            ) THEN 1 ELSE 0 END AS sla_fail_count,

            CASE WHEN (
                SLA_S.reached_datetime IS NOT NULL
                AND (SLA_S.deadline IS NULL OR SLA_S.reached_datetime < SLA_S.deadline)
            ) THEN 1 ELSE 0 END AS sla_success_count,

            CASE WHEN SLA_S.deadline IS NOT NULL THEN 1 ELSE 0 END AS sla_total_count,

            -- Failure rate %: fail / (fail + success) * 100, only when there are concluded checks
            CASE
                WHEN (
                    (CASE WHEN (
                        (SLA_S.reached_datetime IS NOT NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.reached_datetime >= SLA_S.deadline)
                        OR (SLA_S.reached_datetime IS NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC')
                    ) THEN 1 ELSE 0 END)
                    +
                    (CASE WHEN (
                        SLA_S.reached_datetime IS NOT NULL
                        AND (SLA_S.deadline IS NULL OR SLA_S.reached_datetime < SLA_S.deadline)
                    ) THEN 1 ELSE 0 END)
                ) > 0
                THEN ROUND(
                    (CASE WHEN (
                        (SLA_S.reached_datetime IS NOT NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.reached_datetime >= SLA_S.deadline)
                        OR (SLA_S.reached_datetime IS NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC')
                    ) THEN 1.0 ELSE 0.0 END)
                    /
                    (
                        (CASE WHEN (
                            (SLA_S.reached_datetime IS NOT NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.reached_datetime >= SLA_S.deadline)
                            OR (SLA_S.reached_datetime IS NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC')
                        ) THEN 1 ELSE 0 END)
                        +
                        (CASE WHEN (
                            SLA_S.reached_datetime IS NOT NULL
                            AND (SLA_S.deadline IS NULL OR SLA_S.reached_datetime < SLA_S.deadline)
                        ) THEN 1 ELSE 0 END)
                    ) * 100.0
                , 1)
                ELSE NULL
            END AS sla_fail_rate,

            -- Success rate %
            CASE
                WHEN (
                    (CASE WHEN (
                        (SLA_S.reached_datetime IS NOT NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.reached_datetime >= SLA_S.deadline)
                        OR (SLA_S.reached_datetime IS NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC')
                    ) THEN 1 ELSE 0 END)
                    +
                    (CASE WHEN (
                        SLA_S.reached_datetime IS NOT NULL
                        AND (SLA_S.deadline IS NULL OR SLA_S.reached_datetime < SLA_S.deadline)
                    ) THEN 1 ELSE 0 END)
                ) > 0
                THEN ROUND(
                    (CASE WHEN (
                        SLA_S.reached_datetime IS NOT NULL
                        AND (SLA_S.deadline IS NULL OR SLA_S.reached_datetime < SLA_S.deadline)
                    ) THEN 1.0 ELSE 0.0 END)
                    /
                    (
                        (CASE WHEN (
                            (SLA_S.reached_datetime IS NOT NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.reached_datetime >= SLA_S.deadline)
                            OR (SLA_S.reached_datetime IS NULL AND SLA_S.deadline IS NOT NULL AND SLA_S.deadline < NOW() AT TIME ZONE 'UTC')
                        ) THEN 1 ELSE 0 END)
                        +
                        (CASE WHEN (
                            SLA_S.reached_datetime IS NOT NULL
                            AND (SLA_S.deadline IS NULL OR SLA_S.reached_datetime < SLA_S.deadline)
                        ) THEN 1 ELSE 0 END)
                    ) * 100.0
                , 1)
                ELSE NULL
            END AS sla_success_rate
        """
        return select_str
