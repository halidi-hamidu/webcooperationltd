from odoo import api, fields, models, _


class AccountReports(models.TransientModel):
    _inherit = "ins.general.ledger"

    business_line = fields.Selection([
        ('atras', 'IoT VTS'),
        ('ects', 'IoT ECTS'),
        ('itms', 'IT Management & Security Services'),
        ('uis', 'Unified Infrastructure Solutions'),
        ('ictpack', 'Application Software'),
    ], string='Business Line', index=True, readonly=False, copy=False
    )

    def process_filters(self):
        filters_dict = super(AccountReports, self).process_filters()

        if filters_dict:
            if self.business_line:
                filters_dict['business_line'] = self.business_line

        return filters_dict

    def build_where_clause(self, data=False):
        where = super(AccountReports, self).build_where_clause(data=False)

        if where and self.business_line:
            where += "AND m.business_line= '%s'" % self.business_line

        return where

    def get_filters(self, default_filters={}):
        dict = super(AccountReports, self).get_filters(default_filters={})

        if dict and self.business_line:
            dict.update({'business_line': self.business_line})

        return dict
