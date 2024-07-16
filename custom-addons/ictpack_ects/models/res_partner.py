from odoo import fields, models, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_ects_agent = fields.Boolean('ECTS Agent')
    is_credit_customer = fields.Boolean('ECTS Credit Customer')
    is_ects_driver = fields.Boolean("ECTS Driver")
    driver_license = fields.Char("Driver License")

    def return_ects_customers(self):
        partners = self.search([])
        values = []
        if partners:
            for rec in partners:
                value = {
                    "id": rec.id,
                    "name": rec.name,
                    "is_agent": rec.is_ects_agent,
                    "is_credit_customer": rec.is_credit_customer
                }
                values.append(value)
        return values
