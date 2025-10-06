# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle 
#
##############################################################################

from odoo import models,fields, api
from odoo import tools
from datetime import datetime
# ========For Excel=======
from io import BytesIO
import xlrd
import xlwt
from xlwt import easyxf, Formula
import base64
# =======================
import dateutil.relativedelta
from datetime import timedelta
import calendar


class res_partner(models.Model):
    _inherit ='res.partner'

    is_on_date = fields.Boolean('Is On Date')
    overdue_date = fields.Date('Overdue Date')
    aging_by = fields.Selection([('inv_date','Invoice Date'),('due_date','Due Date')],string='Aging By')
    statement_lines = fields.One2many('partner.customer.statement.lines','partner_id')
    partner_overdue_amount = fields.Monetary('Overdue Amount', currency_field = 'statement_currency_id')
    statement_excel_file = fields.Binary('Statement Excel')
    statement_currency_id = fields.Many2one('res.currency', string='Currency')
    
    def set_ageing_date(self):
        over_date=self.overdue_date
        con1 = 31
        con2 = 61
        con3 = 91
        con4 = 121
        con5 = 151
        
        f1 = '0-30'
        d1 = '31-60'
        d2 = '61-90'
        d3 = '91-120'
        d4 = '121 Greater'
        
        not_due = 0.0
        f_pe = 0.0 # 0 -30
        s_pe = 0.0 # 31-60
        t_pe = 0.0 # 61-90
        fo_pe = 0.0 # 91-120
        l_pe = 0.0 # +120
        for line in self.statement_lines:
            ag_date=False
            if self.aging_by == 'due_date':
                ag_date = line.due_date
            else:
                ag_date = line.invoice_date
            if ag_date and self.overdue_date:
                due_date=ag_date
                over_date=self.overdue_date
                if over_date != due_date:
                    if not ag_date > self.overdue_date: 
                        days=over_date - due_date
                        days=int(str(days).split(' ')[0])
                    else:
                        days= -1
                else:
                    days = 0
                
                if days < 0:
                    not_due += line.balance_amount
                elif days < con1:
                    f_pe += line.balance_amount
                elif days < con2:
                    s_pe += line.balance_amount
                elif days < con3:
                    t_pe += line.balance_amount
                elif days < con4:
                    fo_pe += line.balance_amount
                else:
                    l_pe += line.balance_amount
        
        return [{
                'not_due':not_due,
                '0-30': f_pe,
                '31-60': s_pe,
                '61-90': t_pe,
                '91-120': fo_pe,
                '121 Greater': l_pe,
            },[f1,d1,d2,d3,d4]]
            
    def get_month_name(self,day,mon,year):
        year = str(year)
        day = str(day)
        if mon == 1:
            return day+ ' - ' +'JAN'+' - '+year
        elif mon == 2:
            return day+ ' - ' +'FEB'+' - '+year
        elif mon == 3:
            return day+ ' - ' +'MAR'+' - '+year
        elif mon == 4:
            return day+ ' - ' +'APR'+' - '+year
        elif mon == 5:
            return day+ ' - ' +'MAY'+' - '+year
        elif mon == 6:
            return day+ ' - ' +'JUN'+' - '+year
        elif mon == 7:
            return day+ ' - ' +'JUL'+' - '+year
        elif mon == 8:
            return day+ ' - ' +'AUG'+' - '+year
        elif mon == 9:
            return day+ ' - ' +'SEP'+' - '+year
        elif mon ==10:
            return day+ ' - ' +'OCT'+' - '+year
        elif mon == 11:
            return day+ ' - ' +'NOV'+' - '+year
        elif mon == 12:
            return day+ ' - ' +'DEC'+' - '+year
                    
    
    def set_ageing(self):
        over_date=self.overdue_date
        d1=over_date - dateutil.relativedelta.relativedelta(months=1)
        d1=datetime(d1.year,d1.month,1) + timedelta(days=calendar.monthrange(d1.year,d1.month)[1] - 1)
        d1 = d1.date()
        d2=over_date - dateutil.relativedelta.relativedelta(months=2)
        d2=datetime(d2.year,d2.month,1) + timedelta(days=calendar.monthrange(d2.year,d2.month)[1] - 1)
        d2 = d2.date()
        d3=over_date - dateutil.relativedelta.relativedelta(months=3)
        d3=datetime(d3.year,d3.month,1) + timedelta(days=calendar.monthrange(d3.year,d3.month)[1] - 1)
        d3 = d3.date()
        d4=over_date - dateutil.relativedelta.relativedelta(months=4)
        d4=datetime(d4.year,d4.month,1) + timedelta(days=calendar.monthrange(d4.year,d4.month)[1] - 1)
        d4 = d4.date()
        d5=over_date - dateutil.relativedelta.relativedelta(months=5)
        d5=datetime(d5.year,d5.month,1) + timedelta(days=calendar.monthrange(d5.year,d5.month)[1] - 1)
        d5 = d5.date()
        
        
        con1 = int(str(over_date - d1).split(' ')[0])
        con2 = int(str(over_date - d2).split(' ')[0])
        con3 = int(str(over_date - d3).split(' ')[0])
        con4 = int(str(over_date - d4).split(' ')[0])
        con5 = int(str(over_date - d5).split(' ')[0])
        
        f1 = self.get_month_name(over_date.day,over_date.month,over_date.year)
        d1 = self.get_month_name(d1.day,d1.month,d1.year)
        d2 = self.get_month_name(d2.day,d2.month,d2.year)
        d3 = self.get_month_name(d3.day,d3.month,d3.year)
        d4 = self.get_month_name(d4.day,d4.month,d4.year) + ' (UPTO)'
        d5 = self.get_month_name(d5.day,d5.month,d5.year)
        
        not_due = 0.0
        f_pe = 0.0 # 0 -30
        s_pe = 0.0 # 31-60
        t_pe = 0.0 # 61-90
        fo_pe = 0.0 # 91-120
        l_pe = 0.0 # +120
        for line in self.statement_lines:
            ag_date=False
            if self.aging_by == 'due_date':
                ag_date = line.due_date
            else:
                ag_date = line.invoice_date
            if ag_date and self.overdue_date:
                due_date=ag_date
                over_date=self.overdue_date
                if over_date != due_date:
                    if not ag_date > self.overdue_date: 
                        days=over_date - due_date
                        days=int(str(days).split(' ')[0])
                    else:
                        days= -1
                else:
                    days = 0
                
                if days < 0:
                    not_due += line.balance_amount
                elif days < con1:
                    f_pe += line.balance_amount
                elif days < con2:
                    s_pe += line.balance_amount
                elif days < con3:
                    t_pe += line.balance_amount
                elif days < con4:
                    fo_pe += line.balance_amount
                else:
                    l_pe += line.balance_amount
        
        return [{
                'not_due':not_due,
                f1: f_pe,
                d1: s_pe,
                d2: t_pe,
                d3: fo_pe,
                d4: l_pe,
            },[f1,d1,d2,d3,d4]]
            
            
    
    
    def _lines_get(self, partner):
        company = self.env.user.company_id
        move_type = ['out_invoice','out_refund','in_invoice','in_refund']
        query = """ select aml.id from account_move_line as aml \
                    JOIN account_account as aa ON aa.id = aml.account_id \
                    JOIN account_move as am ON am.id = aml.move_id \
                    where aml.date <= %s and aml.partner_id = %s and am.move_type in %s \
                    and aa.account_type = %s and am.state not in %s and am.company_id = %s and aml.move_id is not null"""
        params = (partner.overdue_date, partner.id, tuple(move_type), 'asset_receivable', tuple(['draft','cancel']), company.id)
        
        self.env.cr.execute(query, params)
        result = self.env.cr.dictfetchall()
        movelines = [r.get('id') for r in result]
        movelines = self.env['account.move.line'].browse(movelines)
        partner.statement_currency_id = company.currency_id.id or False
        return movelines, company
    
    def compute_statement_lines(self):
        if not self.overdue_date:
            self.overdue_date = datetime.now()
        if not self.aging_by:
            self.aging_by = 'due_date'
        movelines, company = self._lines_get(self)
        res = []
        ovedue_amount = 0
        for line in movelines:
            inv_amt = 0.0
            paid_amt = 0.0
            inv_amt = line.debit - line.credit
            debit_amount = 0
            credit_amount = 0
            query = """select sum(amount) from account_partial_reconcile as apr JOIN account_move_line as aml ON aml.id = apr.debit_move_id where apr.max_date <= %s and apr.debit_move_id = %s"""
            params = (self.overdue_date, line.id)
            self.env.cr.execute(query, params)
            result = self.env.cr.dictfetchall()
            if result[0].get('sum'):
                debit_amount = result[0].get('sum')
                
            query = """select sum(amount) from account_partial_reconcile as apr JOIN account_move_line as aml ON aml.id = apr.credit_move_id where apr.max_date <= %s and apr.credit_move_id = %s"""
            params = (self.overdue_date, line.id)
            self.env.cr.execute(query, params)
            result = self.env.cr.dictfetchall()
            if result[0].get('sum'):
                credit_amount = result[0].get('sum')
            paid_amt = abs(debit_amount - credit_amount)
            inv_amt = round(inv_amt,2)
            paid_amt = round(paid_amt,2)
            total = float(inv_amt - paid_amt)
            if total > 0 or total < 0:
                ovedue_amount += total
                res.append((0,0,{
                    'invoice_date':line.date,
                    'desc':line.ref or '/',
                    'invoice_number':line.move_id.name or '',
                    'due_date':line.date_maturity or line.date or False,
                    'invoice_amount':float(inv_amt),
                    'payment_amount':float(paid_amt),
                    'balance_amount':float(total),
                    'currency_id':company.currency_id and company.currency_id.id or False,
                }))
            if self.statement_lines:
                self.statement_lines.unlink()
        self.statement_lines = res
        self.partner_overdue_amount = ovedue_amount
    
    def print_statement(self):
        self.compute_statement_lines()
        self.write({'is_on_date':True})
        return self.env.ref('dev_customer_statement_advance.report_customer_statement').report_action(self)
    
    def send_statement(self):
        self.compute_statement_lines()
        template_id = self.env['ir.model.data']._xmlid_to_res_id('dev_customer_statement_advance.dev_partner_send_statement', raise_if_not_found=False)
        mtp = self.env['mail.template']
        template_id = mtp.browse(template_id)
        template_id.send_mail(self.id,force_send=True)
    
    
    def get_partner_address(self):
        partner=self.name + '\n'
        if self.street:
            partner = partner + self.street + '\n'
        if self.street2:
            partner = partner + self.street2 + '\n'
        city = ''
        if self.city:
            city = self.city
        if self.zip:
            city = city +', '+ self.zip
        if city:
            partner = partner + city + '\n'
        if self.country_id:
            partner = partner + self.country_id.name 
        return partner
            
        
    
    def create_excel_header(self, worksheet):
        header_style = easyxf('pattern: pattern solid, fore_colour light_blue;align: horiz center,vert center;'
                              'font: colour white, bold True,height 300;')
        sub_header = easyxf('pattern: pattern solid, fore_colour light_blue;align: horiz center;'
                              'font: colour white, bold True,height 250;')
        content = easyxf('font:height 200;align:vert top')
        content_border = easyxf('font:height 200;align:vert center;' 'borders: top thin,bottom thin,left thin, right thin')
        
        worksheet.write_merge(0, 1, 1, 7, 'Statement Of Account', header_style)
        
        worksheet.write_merge(3,5,0,2,self.get_partner_address(),content_border)
        
        overdue_date = ''
        if self.overdue_date:
            overdue_date = self.overdue_date.strftime("%d-%m-%Y")
        worksheet.write_merge(3,3,4,5,'AS ON',content_border)
        worksheet.write_merge(3,3,6,7,overdue_date,content_border)
        worksheet.write_merge(4,4,4,5,'Credit Term',content_border)
        worksheet.write_merge(4,4,6,7,self.property_payment_term_id.name or ' ',content_border)
        worksheet.write_merge(5,5,4,5,'Currency',content_border)
        worksheet.write_merge(5,5,6,7,self.statement_currency_id.symbol or ' ',content_border)
        
        return worksheet, 7
    
    def create_excel_table(self,worksheet, row):
        sub_header = easyxf('pattern: pattern solid, fore_colour light_blue;align: horiz center,vert center;'
                              'font: colour white, bold True,height 200;')
        text_left = easyxf('font:height 200;align:vert center,horiz left;' 'borders: top thin,bottom thin,left thin, right thin')
        text_center = easyxf('font:height 200;align:vert center,horiz center;' 'borders: top thin,bottom thin,left thin, right thin', num_format_str='0.00')
        
        text_right_pro = easyxf('font:height 200;align:vert center,horiz right;' 'borders: top thin,bottom thin,left thin, right thin;', num_format_str='0.00')
        
        
        text_right_bold = easyxf('font:height 200,bold True;align:vert center,horiz right;' 'borders: top thin,bottom thin,left thin, right thin;' 'protection: formula_hidden 1;', num_format_str='0.00')
        
        worksheet.write(row, 0, 'Description', sub_header)
        worksheet.write(row, 1, 'Invoice Date', sub_header)
        worksheet.write(row, 2, 'Due Date', sub_header)
        worksheet.write(row, 3, 'Invoice #', sub_header)
        worksheet.write(row, 4, 'Invoice Amt', sub_header)
        worksheet.write(row, 5, 'Payment Amt', sub_header)
        worksheet.write(row, 6, 'Balance Due', sub_header)
        row+=1
        for line in self.statement_lines:
            invoice_date = ''
            due_date = ''
            if line.invoice_date:
                invoice_date = line.invoice_date.strftime("%d-%m-%Y")
            if line.due_date:
                due_date = line.due_date.strftime("%d-%m-%Y")
                
            worksheet.write(row, 0, line.desc or '', text_left)
            worksheet.write(row, 1, invoice_date or '', text_center)
            worksheet.write(row, 2, due_date or '', text_center)
            worksheet.write(row, 3, line.invoice_number or '', text_center)
            worksheet.write(row, 4, line.invoice_amount or 0.00, text_right_pro)
            worksheet.write(row, 5, line.payment_amount or 0.00, text_right_pro)
            worksheet.write(row, 6, line.balance_amount or 0.00, text_right_pro)
            row+=1
        return worksheet, row
    
    def create_excel_table_footer(self,worksheet, row):
        row+=2
        if self.is_on_date:
            val1, val2 = self.set_ageing_date()
        else:
            val1, val2 = self.set_ageing()
        sub_header = easyxf('pattern: pattern solid, fore_colour light_blue;align: horiz center,vert center;'
                              'font: colour white, bold True,height 200;')
        text_center = easyxf('font:height 200;align:vert center,horiz center;' 'borders: top thin,bottom thin,left thin, right thin', num_format_str='0.00')
        
        worksheet.write(row, 0, 'Current', sub_header)
        c=1
        for val in val2:
            worksheet.write(row, c, val, sub_header)
            c+=1
        row+=1
        worksheet.write(row, 0, val1.get('not_due'), text_center)
        c=1
        for val in val2:
            worksheet.write(row, c, val1.get(val), text_center)
            c+=1
        return worksheet, row
        
    def generate_excel(self):
        self.is_on_date = True
        val = self.print_excel_statement()
        return val
    
    def print_excel_statement(self):
        filename = 'Customer Statement.xls'
        workbook = xlwt.Workbook()
        worksheet = []
        for l in range(0, len(self)):
            worksheet.append(l)
        i = 0
        for partner in self:
            partner.compute_statement_lines()
            name = partner.name + ' Statement'
            worksheet[i] = workbook.add_sheet(name)
            for r in range(0,20):
                worksheet[i].col(r).width = 150 * 30
            for c in range(0,1000):
                worksheet[i].row(c).height = 350
            worksheet[i].protect = True
            worksheet[i].wnd_protect = True
            worksheet[i].obj_protect = True
            worksheet[i].scen_protect = True
            worksheet[i],row = partner.create_excel_header(worksheet[i])
            worksheet[i], row = partner.create_excel_table(worksheet[i],row)
            worksheet[i], row = partner.create_excel_table_footer(worksheet[i],row)
            
        fp = BytesIO()
        workbook.save(fp)
        fp.seek(0)
        excel_file = base64.encodestring(fp.read())
        fp.close()
        self.write({'statement_excel_file': excel_file})
        active_id = self.ids[0]
        return {'type': 'ir.actions.act_url', 'url': 'web/content/?model=res.partner&download=true&field=statement_excel_file&id=%s&filename=%s' % (active_id, filename), 'target': 'new', }


class partner_customer_statement_lines(models.Model):
    _name = 'partner.customer.statement.lines'
    _description = 'Customer Statement Lines'
    
    invoice_number = fields.Char('Invoice Number')
    desc = fields.Char('Description')
    invoice_date = fields.Date('Invoice Date')
    due_date = fields.Date('Due Date')
    invoice_amount = fields.Monetary('Invoice Amount')
    payment_amount = fields.Monetary('Paid Amount')
    balance_amount = fields.Monetary('Balance Amount')
    partner_id = fields.Many2one('res.partner', string='Partner')
    currency_id = fields.Many2one('res.currency', string='Currency')
    
    
# vim:expandtab:smartindent:tabstop=4:4softtabstop=4:shiftwidth=4:    
