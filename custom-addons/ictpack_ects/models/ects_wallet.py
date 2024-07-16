from odoo import fields, models, api

# Wallet operations are replaced with inventory:


class EctsWallet(models.Model):
    _name = 'ects.wallet'
    _description = 'Ects Wallet'
    _rec_name = 'wallet_id'

    wallet_id = fields.Char('Wallet ID')
    employee_id = fields.Many2one('hr.employee')
    balance = fields.Float('Wallet Amount')
    amount_remained = fields.Float('Wallet Amount Remained')  # Not Important
    lines_ids = fields.One2many('ects.wallet.lines', 'wallet_id')


class EctsWalletLines(models.Model):
    _name = 'ects.wallet.lines'
    _description = 'Ects Wallet Lines'
    _rec_name = 'transaction_id'

    transaction_id = fields.Char('Transaction ID')
    wallet_id = fields.Many2one('ects.wallet')
    amount_added = fields.Float('Amount Added')
    amount_subtracted = fields.Float('Amount Subtracted')

# Wallet will have two Tabs/Pages [ 'Wallet Transfer' , 'Trip Transactions' ]
