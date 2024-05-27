from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class AccountJournal(models.Model):
    _inherit = "account.journal"
    _description = "Journal"

    type = fields.Selection([
            ('sale', 'Sale'),
            ('purchase', 'Purchase'),
            ('cash', 'Cash'),
            ('bank', 'Bank'),
            ('imprest', 'Imprest'),
            ('petty', 'Petty Expenses'),
            ('payment', 'Payment Voucher'),
            ('general', 'Miscellaneous'),
        ], required=True,
        help="Select 'Sale' for customer invoices journals.\n"\
        "Select 'Purchase' for vendor bills journals.\n"\
        "Select 'Cash' or 'Bank' for journals that are used in customer or vendor payments.\n"\
        "Select 'Imprest' for journals that are used in imprest payments.\n"\
        "Select 'General' for miscellaneous operations journals.")