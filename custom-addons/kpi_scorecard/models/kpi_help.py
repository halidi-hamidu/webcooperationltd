#coding: utf-8

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval


help_dict = {
    "kpi.period": _("""
<div>
<p style="padding-bottom:10px;">A KPI period is a time frame for which companies set their targets to control 
performance (in a similar way as financial performance is controlled within accounting/fiscal periods).</p>
<p style="padding-bottom:10px;">KPI scorecards in comparison to simple dashboards assume that you might not only
overview actual figures but compare those to real targets. However, goals should be time-constrained ('Sell as much as
possible' is not a goal, while 'Generate 100,000 Euro Revenue in the year 2023' is a good target for a salesperson, for
example). That is why KPI periods are introduced.</p>
<p style="padding-bottom:10px;">The app allows setting periods of any length including intervals that cross each other
(and even the Past periods!). To open a new KPI period you should just set start and end dates. Those dates will be used
to calculate KPI actual value. For example, a KPI formula might include a basic KPI measurement for the total amount of
sale orders, while the date field of this measurement is defined as 'Order date'. Then, only sale orders whose order
date is within the period will be taken into account. Thus, the KPI scorecard will show the total revenue for a given
period.</p>
<p style="padding-bottom:10px;">It is recommended to have a more or less strict logic of periods for comparability
purposes. Usually, KPI targets are set for a whole year and quarterly/monthly intervals. It lets us not only have a KPI
overview but also check historical trends. The app automatically considers various periods in order to define which
might be compared to this one, and will show users a chart of actual values by a specific KPI. It is possible to define
tolerance on the configuration page. For example, 2-day tolerance is needed to compare quarterly periods (since a
quarter might take from 90 to 92 days), and 3-day tolerance for months (unluckily, February may last 28 days).</p>
<p style="padding-bottom:10px;">When a period end date is already in the Past, it is preferable to close the period to
avoid further updates of KPI targets' actual values due to further corrections (it is not a good idea to update
December KPIs in the next August even though a sale total needs to be corrected, for example). This action is pretty
much the same as when an accountant finishes a fiscal year. To close a period use the button 'Close period' (this action
might be rolled back by re-opening the period).</p>
<p style="padding-bottom:10px;">KPI periods let you also copy targets from existing periods (so, use them as a template).
To that end, just push the button 'Substitute targets' and select a period with proper KPI targets. It significantly
saves time, since KPI targets usually remain similar for periods of the same length. Do not worry, after that action,
you will be still able to change the actual scorecard for this period (for sure, until a period is closed).</p>
<p style="padding-bottom:10px;">Based on KPI periods you may also configure KPI formulas to rely upon period length in
days to calculate figures per day, week, etc. To that end use the special Measurements 'Periods Days' or 'Days Passed'
(how many days already passed in comparison to today) when you construct a formula. For example, you might have an
average sales amount per week within the given period, and compare how much it changes from the previous one. That
length is calculated automatically, while you just put that to a proper formula place.</p>
</div>
    """),
    "kpi.item": _("""
<div>
<p style="padding-bottom:10px;">KPIs (key performance indicators) are measurements that aim to evaluate an
organizational or personal success of a definite activity. Different companies have different KPIs depending on their
strategy and business area. However, all KPIs have a common core attribute: they must be measurable within a target
period.</p>
<p style="padding-bottom:10px;">To that end, KPIs allow constructing formulas to retrieve Odoo data sets and process
those into real figures. Formula preparation is as simple as it is to write down a mathematical expression: just drag
and drop formula parts in the correct order with the correct operators.</p>
<h3>KPIs, KPI periods, and KPI targets</h3>
<p style="padding-bottom:10px;">KPIs represent the list of success figures you may use to plan your company activities.
Simultaneously, measurements are almost senseless unless you have target values for those KPIs. That is possible only
within a time-constrained period. 'Sell as much as you can' is not a goal, while 'Generate 100,000 Euro Revenue in the
year 2023' is a good aim for a salesperson, for example. To that goal, KPI periods are introduced.</p>
<p style="padding-bottom:10px;">A combination of a KPI and a KPI period results in a KPI target. Exactly with those
targets you work on the scorecard interface. For each KPI, you would like to manage in this period, you should define a
planned value to compare those to the actual at the end of the period.</p>
<p style="padding-bottom:10px;">So, a KPI itself defines how to compute an actual value for a period and how to estimate
the result ('the more the better' or 'the less the better'), but does not assume setting targets. The latter should be
done for each period.</p>
<h3>Formula parts</h3>
<p style="padding-bottom:10px;">As variables for the KPI formula you may use:</p>
<p style="padding-bottom:10px;"><i>Measurements (KPI measurements, KPI variables)</i> are figures calculated from actual
Odoo data for a checked period. For example, 'number of quotations of the sales team Europe'.</p>
<p style="padding-bottom:10px;">Among measurements you may also find 2 very specific variables: 'Period Days' and 'Days
Passed'. Those figures are calculated not from Odoo data, but from the KPI period settings under consideration. 'Period
Days' is an interval length in days. 'Days Passed' is the length between a period start and today (if today is before a
period end; otherwise period end). Those parameters let calculate per-time KPIs, such as, for example, 'Average sales
per week'.</p>
<p style="padding-bottom:10px;"><i>Constants (KPI constants)</i> are fixed numbers applied globally or for a period.
Such numbers do not depend on Odoo data. So, they let define strict non-changeable figures which you can't otherwise get
from Odoo. For example, 'Total investments'.</p>
<p style="padding-bottom:10px;"><i>Other KPIs</i> are the results of other KPI formula calculations. That variables let
construct derivative complex calculations. For example, you may have KPIs 'Sales count' and 'Opportunities count', and a
derivative KPI 'Opportunity to sales success ratio'.</p>
<p style="padding-bottom:10px;">Variables of any types above might be added to a formula. You may drag and drop as many
variables as you like (and even use the same variable twice). Just do not forget to add operators in between to make
correct mathematical expressions. The following operators are available:</p>
<ul>
<li>"-" - subtraction;</li>
<li>"+" - addition;</li>
<li>"*" - multiplication;</li>
<li>"/" - division;</li>
<li>"(", ")" - to make proper calculation order as it is in Math;</li>
<li>"**" - exponentiation (**2 – squaring; **0.5 – square root extraction);</li>
<li>Float number.</li>
</ul>
<h3>Result appearance</h3>
<p style="padding-bottom:10px;">Depending on the business logic of the KPI formula, the final calculation result might
look differently:</p>
<ul>
<li>Simple number: for example, 'Average sales count per week';</li>
<li>Percentage: for example, 'Sales to opportunities success ratio';</li>
<li>Monetary: for example, 'Total Sales per period'. <strong>Make sure the measurement field you used is in the same
currency (usually, it is a company's default currency)!</strong></li>
</ul>
<p style="padding-bottom:10px;">For simple numbers and percentages, you may also define a result suffix and prefix to
make a figure nice looking (e.g. add "%" as a suffix to have "88<strong>%</strong>"). For monetary result type, it is
recommended to define a currency, which symbol would be added to the final result.</p>
<p style="padding-bottom:10px;">Finally, you may decide how the calculation result should be rounded. Available options
are from 0 to 4 decimal points (1 > 1.2 > 1.23 > 1.235 > 1.2346).</p>
<h3>Categories and hierarchy</h3>
<p style="padding-bottom:10px;">To make navigation by KPI targets more comfortable, KPIs are combined into KPI
categories. It lets not only quickly search targets inside a scorecard, but it allows granting additive access rights.
In this way, users will overview only their KPIs structured in sections.</p>
<p style="padding-bottom:10px;">Each KPI might also have a parent. Such a hierarchy lets organize the KPI scorecard with
indicative padding. For example, 'Total company sales' might have children 'Sales Europe' and 'Sales America'. The
latter 2 might be further specified by salespersons.</p>
<h3>Additive access to KPIs and targets</h3>
<p style="padding-bottom:10px;">By default, KPIs and their linked targets are available only for users with the right
'KPI Manager'. Simultaneously, you may grant extra rights for other user groups or/and definite users. To that goal, it
is possible to define 'Read Rights' and 'Edit Rights' on KPI category or KPI form views (take into account that KPI
category rights and KPI own rights are combined!).</p>
<p style="padding-bottom:10px;">Read rights define which user and user groups are able to observe KPI targets on the
scorecard interface. For example, you might want to share tasks' personal targets with related project users, so they
may control themselves.</p>
<p style="padding-bottom:10px;">Edit rights assume sharing access to set specific targets up. For instance, you may find
it reasonable to involve a sales manager to set sub-targets for their sales team.</p>
<p style="padding-bottom:10px;">Take into account: all security settings are additive and they are not restrictive. KPI
managers will have full rights for all KPIs disregarding those settings, while other users will have rights only to KPIs
which settings (or category settings) allow them so.</p>
</div>
    """),
    "kpi.measure.item": _("""
<div>
<p style="padding-bottom:10px;">A KPI measurement is a final variable used for KPI(s) calculations. It represents a
specification of basic measurement. For example, 'a number of quotations of the sales team Europe' might be a precision
of a basic measurement 'total number of sales orders'.</p>
<p style="padding-bottom:10px;">Such an approach significantly simplifies variables' preparation, since each basic
measurement might have an unlimited number of linked KPI measurements. So, the only thing you need to do is to apply
extra filters (in the example 'Sales Team Name is Europe')..</p>
<p style="padding-bottom:10px;">Take into account that basic measurements of the type 'Execute Python code' cannot be
any more specified since they do not relate to any records. In such a case, there is no sense to have a few KPI
measurements.</p>
<p style="padding-bottom:10px;">In a multi-company environment, KPI Measurements are applied globally or for each
company individually. In the former case, that variable is available for any company KPI formulas, while in the
latter – only for a specific one (it lets make a quicker overview while constructing formulas).</p>
</div>
    """),
    "kpi.constant": _("""
<div>
<p style="padding-bottom:10px;">A KPI constant is a variable type used for formula construction. In comparison to
measurements, KPI constants are fixed and they do not depend on actual Odoo data. It lets introduce figures
that can not be retrieved from modules and/or which should remain the same during the whole period.</p>
<p style="padding-bottom:10px;">For example, you might set the 'total size of investments' to calculate the return on
investments, or the 'number of salesmen' to get sales revenue per person.</p>
<p style="padding-bottom:10px;">A KPI constant value might be defined for each individual period. If the value does not
exist for a calculated period, the app will try to check the parent time frame. For instance, if this constant value is
not set up for January 2022, the app will take all the intervals that include January (e.g. Quarter 1 2022 and the year
2022 consequentially). In case the values are also not defined for those periods, then, the global value will be
applied.</p>
</div>
    """),
    "kpi.measure": _("""
<div>
<p style="padding-bottom:10px;">Basic measurement is the core object used to retrieve actual KPI values from Odoo data.
Although basic measurements are not used themselves for formula constructions, they are required to prepare any sort of
formula variables (KPI measurements).</p>
<p style="padding-bottom:10px;">Any basic measurement represents the most general calculation, while KPI measurements
specify those. For example, 'the total number of sales orders' should be a basic measurement, while narrower 'number of
quotations of the sales team Europe' is recommended to be a precision of that basic measurement (so, KPI measurement).
Each basic measurement might have an unlimited number of linked KPI measurements.</p>
<h3>Calculation Types</h3>
<p style="padding-bottom:10px;">Basic measurements assume a few types of low-level calculations:</p>
<ul>
<li>Counting records, e.g. the number of registered leads or the number of posted customer invoices. Such measurements
should have the KPI type 'Count of records'.</li>
<li>Summing up a certain property of records, e.g. a sum of all orders amount total or sum of paid taxes by invoices.
Such measurements should have the KPI type 'Sum of records field'.</li>
<li>Getting of average for records' number fields, e.g. average planned hours per task or average days to assign a lead.
Such measurements should have the KPI type 'Average of records field'.</li>
<li>Executing Python code. This type requires technical knowledge but lets you compute any sort of figures based on any
Odoo data. Introduce your Python code and save the value into the special variable 'result'. Here you might also use the
special KPI period-related variables: 'period_start' (the first date of the period), 'period_end' (the last date of the
period), 'period_company_id' - res.company object for which Odoo makes calculations at the moment (according to KPI
period).</li>
</ul>
<h3>Basic Measurement Settings</h3>
<p style="padding-bottom:10px;">The first 3 calculation types assume that you define how records should be searched and
which record fields should be used for computations.</p>
<ul>
<li><i>Model</i> is an Odoo document type you have in your database. For example, 'Sales Order' or 'Task'. Here you can
rely not only upon standard Odoo objects but also on Odoo reports. The latter is quite useful if indicators are already
calculated for any existing dashboard (for example, total sales amount in default currency from the 'Sales Analysis
Report').</li>
<li><i>Date fields</i> are required to understand whether a specific document type relates to a considered period, so,
how to distribute objects by time intervals. For example, for tasks, you might use 'create date' to analyze jobs
registered within this KPI period (e.g. 'Total number of tasks created in January 2022'). It is possible to apply a few
date fields (e.g. 'Opportunities opened and won in January 2022'). If date fields are not specified, the KPI period will
not influence this basic measurement.</li>
<li><i>Filters</i> allow you to restrict records set by any stored field. For example, you may calculate a count of only
won opportunities based on stage settings or only posted customer invoices based on journal entry type and state.</li>
<li><i>Measure field</i> is available and required only for calculation types 'Average' and 'Sum'. It defines which
figure you use for calculations. For example, the total amount of Sales Analysis Report to get accumulated sales revenue
or work hours of tasks to get the average spent time per task</li>
<li><i>Company field</i> will be needed for multi companies environments. According to that field, KPIs are considered
only within a target company's KPI period. Take into account that records without company will be used for all
companies' KPI calculations.</li>
</ul>
<p style="padding-bottom:10px;">All settings might relate to your custom objects or custom fields, including ones
created through the interface or the Odoo studio.</p>
</div>
    """),
    "kpi.category": _("""
<div>
<p style="padding-bottom:10px;">KPI categories are used to structure KPIs and KPI targets for comfortable navigation.
Each KPI should be assigned to a single category, which allows users to find required targets quickly just by checking
the boxes on the scorecard interface.</p>
<p style="padding-bottom:10px;">The hierarchy of categories lets users also combine targets in sections to control KPIs
related to specific areas. For example, to check targets only in sales (e.g. the category 'sales') or targets of a
specific sales team (e.g. the category 'sales > sales team Europe').</p>
<p style="padding-bottom:10px;">MMoreover, KPI categories let you administrate user accesses in a batch. Thus, you may
grant users and/or user groups access to this category KPI ('Read Rights') or a right to update those targets ('Edit
rights)'. Then, there will be no need to manage each KPI separately. Take into account that those settings are additive,
not restrictive, meaning that KPI managers will anyway have full rights for all KPIs.</p>
</div>
    """),
    "kpi.scorecard.line": _("""
<p style="margin-bottom:0; padding-bottom: 10px;">A KPI target is your plan for this KPI for a given period. By setting up a target
value, you indicate which result you would like to achieve by the end of the period.</p>
<p style="padding-bottom:10px;">KPI targets actual values are re-calculated regularly (not in real-time) and
automatically by the Odoo cron job. Alternatively, you may press the button 'Calculate' on the left navigation bar.</p>
"""),
    "kpi.copy.template": _("""
<p>This action will replace all the current targets with the targets from a chosen period. After the action, you will be
still able to modify the scorecard: change targets' values, delete certain KPI targets or add new ones.</p>"""),
}


class kpi_help(models.AbstractModel):
    """
    The model to store help settings
    """
    _name = "kpi.help"
    _description = "KPI Help"

    @api.depends("kpi_help_dummy")
    def _compute_show_kpi_help(self):
        """
        Compute method for show_kpi_help
            
        Extra info:
         * kpi_help_dummy is required to have something in depends and to calculate it on all forms
        """
        Config = self.env["ir.config_parameter"].sudo()
        help_setting = safe_eval(Config.get_param("kpi_scorecard.show_kpi_help", "False"))
        help_notes = help_setting and help_dict.get(self._name) or False
        for record in self:
            record.help_notes = help_notes

    help_notes = fields.Html(string="Help", compute=_compute_show_kpi_help)
    kpi_help_dummy = fields.Boolean("Dummy Help")
