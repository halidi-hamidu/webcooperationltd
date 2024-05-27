from odoo import fields, models, api

class PaymentReceiptPaymentType(models.Model):
    _name = 'payment.receipt.payment.type'
    _description = 'Payment Type'

    name = fields.Char(required=True)
    key = fields.Char(required=True)
    description = fields.Char()
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)


class PaymentReceiptTaxType(models.Model):
    _name = 'payment.receipt.tax.type'
    _description = 'Tax Type'

    name = fields.Char(required=True)
    key = fields.Char(required=True)
    rate = fields.Float(required=True, string='Tax Rate')
    description = fields.Char()
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

class PaymentReceiptIdentityType(models.Model):
    _name = 'payment.receipt.identity.type'
    _description = 'Identity Type'

    name = fields.Char(required=True)
    key = fields.Char(required=True)
    description = fields.Char()
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)