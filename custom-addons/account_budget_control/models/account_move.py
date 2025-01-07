# -*- coding: utf-8 -*-
#############################################################################
#
#    IctPack Solutions Ltd.
#
#    Copyright (C) 2022-TODAY IctPack Solutions Ltd
#    Author: IctPack Solutions Ltd
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        if self.move_type == 'entry':
            return super(AccountMove, self).action_post()
        else:
            indicator = True
            for line in self.invoice_line_ids:
                if line.crossovered_budget_id.type == 'expenditure' or line.crossovered_budget_id.type == 'project':
                    total_sum = line.price_subtotal
                    for sm in self.invoice_line_ids:
                        if (sm.budget_line_id == line.budget_line_id) and (sm.id != line.id):
                            total_sum += line.price_subtotal
                            
                    if line.budget_line_id.allocated_balance >= total_sum:
                        indicator =  True
                    else:
                        indicator =  False

            if indicator:
                return super(AccountMove, self).action_post()
            else:
                raise ValidationError(_("Can not Authorize the invoice, as the Budget line(s) chosen do not have enough funds or No Bugdet Lines have been added"))


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    crossovered_budget_id = fields.Many2one('crossovered.budget', 'Budget', domain="[('state','=','validate')]")
    budget_line_id = fields.Many2one('crossovered.budget.lines', 'Budget Line',
                                     domain="[('crossovered_budget_state','=','validate'),('crossovered_budget_id','=?',crossovered_budget_id)]")

    @api.onchange('budget_line_id')
    def budget_line_id_change(self):
        if self.budget_line_id:
            setattr(self, 'analytic_distribution',{self.budget_line_id.analytic_account_id.id:100})
            setattr(self, 'account_id', self.budget_line_id.general_budget_id.account_ids.id)
