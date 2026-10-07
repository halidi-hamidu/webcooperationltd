# -*- coding: utf-8 -*-
#################################################################################
#
# Copyright (c) 2013-Present IctPack Solutions LTD. (<http://ictpack.com>)
#
#################################################################################

from markupsafe import Markup, escape
from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    expense_id = fields.Many2one(
        comodel_name='hr.expense',
        string='Linked Expense',
        readonly=True,
        copy=False,
        tracking=True,
        ondelete='set null',
        help="Expense record created from this approval request.",
    )
    expense_state = fields.Selection(
        related='expense_id.state',
        string='Expense Status',
    )

    def action_create_expense(self):
        """Create an hr.expense from this approved approval request and navigate to it."""
        self.ensure_one()

        if self.request_status != 'approved':
            raise UserError(_(
                "The approval request must be fully approved before creating an expense."
            ))
        if self.expense_id:
            raise UserError(_(
                "An expense record has already been created for this approval request."
            ))

        # Find the employee linked to the request owner in the same company
        employee = self.env['hr.employee'].search([
            ('user_id', '=', self.request_owner_id.id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not employee:
            raise UserError(_(
                "No employee record found for '%s'. "
                "Please ensure the requester is linked to an employee record in company '%s'.",
                self.request_owner_id.name,
                self.company_id.name,
            ))

        # Use the generic "Expenses" product (zero cost) so the amount is freely settable;
        # HR will select the correct expense category (product) on the expense form.
        default_product = self.env.ref(
            'hr_expense.product_product_no_cost', raise_if_not_found=False
        )

        # Resolve expense date: prefer date, fall back to date_start, then today
        expense_date = (
            self.date.date() if self.date else
            self.date_start.date() if self.date_start else
            fields.Date.today()
        )

        expense_vals = {
            'name': self.name,
            'employee_id': employee.id,
            'total_amount_currency': self.amount or 0.0,
            'date': expense_date,
            'company_id': self.company_id.id,
            'payment_mode': 'own_account',
            'description': html2plaintext(self.reason) if self.reason else False,
        }
        if default_product:
            expense_vals['product_id'] = default_product.id

        expense = self.env['hr.expense'].create(expense_vals)
        self.expense_id = expense.id

        self.message_post(
            body=Markup('%s <a href="/web#model=hr.expense&id=%s"><b>%s</b></a>.') % (
                escape(_('Expense created from this approval request:')),
                expense.id,
                escape(expense.display_name),
            ),
            body_is_html=True,
        )
        expense.message_post(
            body=Markup('%s <a href="/web#model=approval.request&id=%s"><b>%s</b></a>.') % (
                escape(_('Created from approval request:')),
                self.id,
                escape(self.display_name),
            ),
            body_is_html=True,
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.expense',
            'res_id': expense.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_expense(self):
        """Navigate to the linked expense record."""
        self.ensure_one()
        if not self.expense_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.expense',
            'res_id': self.expense_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


