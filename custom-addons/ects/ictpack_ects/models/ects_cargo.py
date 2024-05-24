from odoo import fields, models, api


class EctsCargo(models.Model):
    _name = 'ects.cargo'
    _description = 'ECTS Cargo'

    name = fields.Char()


class EctsCargoType(models.Model):
    _name = 'ects.cargo.type'
    _description = 'Cargo Type'

    name = fields.Char(required=True)
    key = fields.Char(required=True)
    description = fields.Char()
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency')
    master_price = fields.Monetary(currency_field='currency_id')
    slave_price = fields.Monetary(currency_field='currency_id')
    credit_master_price = fields.Monetary(currency_field='currency_id')
    credit_slave_price = fields.Monetary(currency_field='currency_id')
