# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle 
#
##############################################################################
from odoo import api, fields, models, _
import datetime
import calendar
     

class dev_due_partner(models.TransientModel):
    _name = "dev.due.partner"
    _description='Due Partner Statement'
    
    
    date = fields.Date('Upto Date', default=datetime.date.today(), required="1")
    aging_by = fields.Selection([('inv_date','Invoice Date'),('due_date','Due Date')],string='Ageing By', default='due_date', required="1")
    
    
    def get_due_partner(self):
        partner_ids = self.env['res.partner'].sudo().search([])
        part_ids = []
        partner_ids.write({
            'overdue_date':self.date,
            'aging_by':self.aging_by,
        })
        for partner in partner_ids:
            partner.compute_statement_lines()
            if partner.partner_overdue_amount != 0:
                part_ids.append(partner.id)
        return part_ids
        
    def view_due_partner(self):
        part_ids = self.get_due_partner()
        partner_ids = self.env['res.partner'].sudo().browse(part_ids)
        partner_ids.write({'is_on_date':True})
        action = self.env["ir.actions.actions"]._for_xml_id("dev_customer_statement_advance.action_view_dev_due_partner")
        if part_ids:
            action['domain'] = [('id', 'in', part_ids)]
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action
    
    def print_excel_statement(self):
        part_ids = self.get_due_partner()
        partner_ids = self.env['res.partner'].sudo().browse(part_ids)
        partner_ids.write({'is_on_date':True})
        val = partner_ids.generate_excel()
        return val
    
    def print_statement(self):
        part_ids = self.get_due_partner()
        partner_ids = self.env['res.partner'].sudo().browse(part_ids)
        partner_ids.write({'is_on_date':True})
        datas = {
		        'form': part_ids,
		    }
        return self.env.ref('dev_customer_statement_advance.report_customer_statement').report_action(self, data=datas)


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
