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
     

class dev_customer_statement(models.TransientModel):
    _name = "dev.customer.statement"
    _description = 'Customer Statement'
    
    month = fields.Selection([('1','JAN'),('2','FEB'),('3','MAR'),('4','APR'),('5','MAY'),('6','JUN'),('7','JUL'),('8','AUG'),('9','SEP'),('10','OCT'),('11','NOV'),('12','DEC')])
    aging_by = fields.Selection([('inv_date','Invoice Date'),('due_date','Due Date')],string='Ageing By', default='due_date', required="1")
    
    is_on_date = fields.Boolean('On Date')
    
    date_upto = fields.Date('Upto Date',required="1", default=datetime.date.today())
    is_privious_year = fields.Boolean('Print Previous Year')

    @api.onchange('month','is_privious_year')
    def onchange_month(self):
        if self.month:
            a= self.month
            a = int(a)
            date=datetime.datetime.now()
            if self.is_privious_year:
                month_end_date=datetime.datetime(date.year-1,a,1) + datetime.timedelta(days=calendar.monthrange(date.year-1,a)[1] - 1)
                self.date_upto = month_end_date.date()
            else:
                month_end_date=datetime.datetime(date.year,a,1) + datetime.timedelta(days=calendar.monthrange(date.year,a)[1] - 1)
                self.date_upto = month_end_date.date()

    
    def print_excel_statement(self):
        partner = self.env['res.partner']
        part_ids=self._context.get('active_ids')
        partner_ids = partner.browse(part_ids)
        if partner_ids:
            partner_ids.write({'overdue_date':self.date_upto,'aging_by':self.aging_by,'is_on_date':self.is_on_date})
        val = partner_ids.print_excel_statement()
        return val
        
        
    def send_statement(self):
        partner = self.env['res.partner']
        part_ids=self._context.get('active_ids')
        partner_ids = partner.browse(part_ids)
        if partner_ids:
            partner_ids.write({'overdue_date':self.date_upto,'aging_by':self.aging_by,'is_on_date':self.is_on_date})
        
        ir_model_data = self.env['ir.model.data']
        template_id = self.env['ir.model.data']._xmlid_to_res_id('dev_customer_statement_advance.dev_partner_send_statement', raise_if_not_found=False)
        mtp = self.env['mail.template']
        template_id = mtp.browse(template_id)
        for partner in partner_ids:
            template_id.send_mail(partner.id,force_send=True)

    def print_statement(self):
        partner = self.env['res.partner']
        part_ids=self._context.get('active_ids')
        partner_ids = partner.browse(part_ids)
        
        if partner_ids:
            partner_ids.write({'overdue_date':self.date_upto,'aging_by':self.aging_by, 'is_on_date':self.is_on_date})
            for partner in partner_ids:
                partner.compute_statement_lines()
        datas = {
		        'form': partner_ids.ids
		    }
        return self.env.ref('dev_customer_statement_advance.report_customer_statement').report_action(self, data=datas)
    



# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
