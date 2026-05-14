# -*- coding: utf-8 -*-
from odoo import models
from . utils import format_response


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    def create_vts_expense(self, vals):
        """
        Create a draft expense from the mobile app.

        Expected vals:
            employee_id (int)  : ID of the hr.employee submitting the expense
            total_amount (float): Amount of the expense
            name (str)         : Description / expense name
            attachments (list) : Optional list of dicts with keys:
                                    name, datas (base64 string), mimetype
        """
        employee_id = vals.get('employee_id')
        total_amount = vals.get('total_amount')
        name = vals.get('name', 'Mobile Expense')
        attachment_vals = vals.get('attachments', [])
        description = vals.get('description', '')

        if not employee_id:
            return format_response('error', 'employee_id is required.', None)

        if not total_amount:
            return format_response('error', 'total_amount is required.', None)

        employee = self.env['hr.employee'].browse(employee_id)
        if not employee.exists():
            return format_response('error', 'Employee not found.', None)

        # Resolve the default expense product (EXP_GEN)
        product = self.env['product.product'].search(
            [('default_code', '=', 'EXP_GEN')], limit=1
        )
        if not product:
            return format_response('error', 'Expense product with default_code EXP_GEN not found.', None)

        expense = self.sudo().create({
            'name': name,
            'employee_id': employee_id,
            'product_id': product.id,
            'total_amount': total_amount,
            'payment_mode': 'company_account',
            'description': description,
        })

        # Attach any uploaded files
        for attachment in attachment_vals:
            self.env['ir.attachment'].sudo().create({
                'name': attachment.get('name', 'attachment'),
                'datas': attachment.get('datas'),
                'mimetype': attachment.get('mimetype', 'application/octet-stream'),
                'res_model': 'hr.expense',
                'res_id': expense.id,
            })

        return format_response(
            'success',
            'Expense created successfully.',
            {'id': expense.id, 'name': expense.name, 'state': expense.state},
        )
    
    _UPDATABLE_EXPENSE_FIELDS = {'total_amount', 'name', 'description'}

    def update_vts_expense(self, vals):
        expense = self.sudo().browse(vals.get('expense_id'))
        employee_id = vals.get('employee_id')

        error = (
            (not expense.exists() and 'Expense not found.') or
            (expense.employee_id.id != employee_id and 'Access denied: this expense does not belong to you.') or
            (expense.state != 'draft' and 'Only draft expenses can be updated.')
        )
        if error:
            return format_response('error', error, None)

        write_vals = {k: v for k, v in vals.items() if k in self._UPDATABLE_EXPENSE_FIELDS}
        if write_vals:
            expense.write(write_vals)

        for attachment in vals.get('attachments', []):
            self.env['ir.attachment'].sudo().create({
                'name': attachment.get('name', 'attachment'),
                'datas': attachment.get('datas'),
                'mimetype': attachment.get('mimetype', 'application/octet-stream'),
                'res_model': 'hr.expense',
                'res_id': expense.id,
            })

        return format_response(
            'success',
            'Expense updated successfully.',
            {'id': expense.id, 'name': expense.name, 'state': expense.state},
        )

    def return_employee_expenses(self, employee_id, domain=[], limit=25):
        """Return a list of expenses for a given employee."""
        if not domain:
            domain = [('state', 'not in', ['posted', 'submitted', 'approved', 'paid'])]
        expenses = self.sudo().search(
            [('employee_id', '=', employee_id)] + domain,
            limit=limit,
            order='date desc',
        )
        values = []
        for expense in expenses:
            values.append({
                'id': expense.id,
                'name': expense.name,
                'manager_name': expense.manager_id.name if expense.manager_id else False,
                'total_amount': expense.total_amount,
                'date': str(expense.date) if expense.date else False,
                'state': expense.state,
                'payment_mode': expense.payment_mode,
            })
        return format_response('success', 'Employee expenses returned successfully.', values)

    def return_expense_details(self, expense_id, employee_id):
        """Return details of a single expense including its attachments."""
        expense = self.sudo().browse(expense_id)
        if not expense.exists():
            return format_response('error', 'Expense not found.', None)

        if expense.employee_id.id != employee_id:
            return format_response('error', 'Access denied: this expense does not belong to you.', None)

        attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'hr.expense'),
            ('res_id', '=', expense.id),
        ])
        attachment_data = [
            {
                'id': att.id,
                'name': att.name,
                'mimetype': att.mimetype,
                'url': f'/web/content/{att.id}?download=true',
            }
            for att in attachments
        ]

        vals = {
            'id': expense.id,
            'name': expense.name,
            'total_amount': expense.total_amount,
            'date': str(expense.date) if expense.date else False,
            'state': expense.state,
            'payment_mode': expense.payment_mode,
            'product': expense.product_id.name if expense.product_id else False,
            'employee': expense.employee_id.name if expense.employee_id else False,
            'description': expense.description if expense.description else False,
            'attachments': attachment_data,
        }
        return format_response('success', 'Expense details returned successfully.', vals)
