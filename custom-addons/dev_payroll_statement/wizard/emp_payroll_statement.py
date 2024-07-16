 ##############################################################################
#    
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Devintelle Solutions (<http://devintellecs.com/>).
#
##############################################################################

from odoo import api, fields, models, _
import time
import itertools
from operator import itemgetter
import operator
from datetime import datetime
import xlwt
from xlsxwriter.workbook import Workbook
from io import BytesIO
import base64
from odoo import tools
from xlwt import easyxf
from odoo.exceptions import ValidationError
import csv


class emp_payroll_statement(models.TransientModel):
    _name = "emp.payroll.statement"

    start_date = fields.Date("Start Date", required="1")
    end_date = fields.Date("End Date", required="1")
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.user.company_id,required="1")
    employee_ids = fields.Many2many("hr.employee", string="Employee")
    
    
    def print_pdf(self):
        if not self.employee_ids:
            raise ValidationError(_('Please Select Employee !!!'))
            
        payslip_ids= self.get_payslip()
        if not payslip_ids:
            raise ValidationError(_('Payslip not found !!!'))
        return self.env.ref('dev_payroll_statement.print_payroll_statement').report_action(self, data=None)
    
    
    def get_payslip(self):
        sql_query = """select ps.id from hr_payslip as ps left join hr_employee as emp on ps.employee_id = emp.id where ps.company_id = %s and ps.employee_id in %s and ps.date_from >= %s and ps.date_to <= %s"""
        params = (self.company_id.id, tuple(self.employee_ids.ids), self.start_date,self.end_date)
        self.env.cr.execute(sql_query, params)
        results = self.env.cr.dictfetchall()
        payslip_ids = [payslip.get('id') for payslip in results]
        return payslip_ids
    
    
    def get_code_list(self,payslip_ids):
        sql_query = """select psl.salary_rule_id as rule_id from hr_payslip_line as psl join hr_payslip as ps on ps.id = psl.slip_id where ps.id in %s"""
        params = (tuple(payslip_ids),)
        self.env.cr.execute(sql_query, params)
        results = self.env.cr.dictfetchall()
        rule_lst = [line.get('rule_id') for line in results]
        rule_ids = self.env['hr.salary.rule'].search([('id','in',rule_lst)],order='sequence')
        lst = []
        for rule in rule_ids:
            lst.append(rule.code)
        return lst
        
    def get_payslip_line_val(self,payslip,code):
        sql_query = """select psl.quantity,psl.rate,psl.amount from hr_payslip_line as psl where psl.slip_id = %s and psl.code = %s"""
        params = (payslip.id,code)
        self.env.cr.execute(sql_query, params)
        results = self.env.cr.dictfetchall()
        if results:
            amount=(results[0].get('amount') * results[0].get('quantity') * results[0].get('rate')) / 100
            return amount
        return 0
        
        
    def get_line_val(self,payslip,code_list):
        val_lst=[]
        for code in code_list:
            val=self.get_payslip_line_val(payslip,code)
            val_lst.append(val)
        return val_lst
        
        
    def get_lines(self,payslip_ids,code_list):
        lines=[]
        for payslip in self.env['hr.payslip'].browse(payslip_ids):
            #payslip_date = datetime.strptime(payslip.date_from, '%Y-%m-%d') 
            month = payslip.date_from.strftime("%B")
            line_val=self.get_line_val(payslip,code_list)
            dic={
                'month':month,
                'bank_account':payslip.employee_id and payslip.employee_id.bank_account_id and payslip.employee_id.bank_account_id.acc_number or '',
                'description':payslip.name or '',
                'employee':payslip.employee_id and payslip.employee_id.name or '',
                'department':payslip.employee_id and payslip.employee_id.department_id and payslip.employee_id.department_id.name or '',
                'lines':line_val,
            }
            lines.append(dic)
        n_lines=sorted(lines,key=itemgetter('month'))
        groups = itertools.groupby(n_lines, key=operator.itemgetter('month'))
        lines = [{'month':k,'values':[x for x in v]} for k, v in groups]    
        return lines

    def get_totals(self, lines, code_list):
        lst = []
        for c in code_list:
            lst.append(0)

        for line in lines:
            i = 0
            for l_val in line.get('lines'):
                lst[i] += l_val
                i += 1
        return lst

        
    def print_excel(self):
        if not self.employee_ids:
            raise ValidationError(_('Please Select Employee !!!'))
            
        payslip_ids= self.get_payslip()
        if not payslip_ids:
            raise ValidationError(_('Payslip not Found !!!'))
            
        filename='Employee Payroll Statement.xls'
        workbook = xlwt.Workbook()
        worksheet = workbook.add_sheet('Payroll Statement')

        # Style
        header_style = easyxf(
            'font:height 300;pattern: pattern solid, fore_color gray25; align: horiz center;font:bold True;')
        line_header = easyxf('font:height 200;align: horiz center;font:bold True;')
        group_line = easyxf('font:height 200;pattern: pattern solid, fore_color gray25; align: horiz left;font:bold True;font:italic True;')
        text_right = easyxf('align: horiz right;', num_format_str='0.00')
        
        text_bold = easyxf('font:height 200;align: horiz center;font:bold True;')
        text_right_bold = easyxf('font:height 200;align: horiz right;font:bold True;', num_format_str='0.00')
        
        #column width 
        worksheet.col(0).width = 55 * 55
        worksheet.col(1).width = 100 * 100
        worksheet.col(2).width = 80 * 80
        
        
        worksheet.write_merge(1, 2, 1, 2, 'Employee Payroll Statement',header_style)
        
        #format_start = datetime.strptime(self.start_date,'%Y-%m-%d')
        #start = format_start.strftime('%d-%m-%Y')
        worksheet.write(1, 3, 'Start Date',line_header)
        worksheet.write(1, 4,self.start_date.strftime("%d/%m/%Y"))
        
        
        #format_end = datetime.strptime(self.end_date,'%Y-%m-%d')
        #end = format_end.strftime('%d-%m-%Y')
        worksheet.write(2, 3, 'End Date',line_header)
        worksheet.write(2, 4, self.end_date.strftime("%d/%m/%Y"))
        
        
        worksheet.write(4, 0, "Company",line_header)
        worksheet.write(4, 1, self.company_id.name,text_right)
        
        
        
        # Values 
        code_list = self.get_code_list(payslip_ids)
        line_values= self.get_lines(payslip_ids,code_list)
        
        r=6
        worksheet.write(r, 0, "Month",line_header)
        worksheet.write(r, 1, "Employee Name",line_header)
        worksheet.write(r, 2, 'Department',line_header)
        c=2
        for code in code_list:
            c+= 1
            worksheet.write(r, c, code ,line_header)
        rc= c
        for line in line_values:
            r+=1
            worksheet.write_merge(r, r, 0, rc, line.get('month') ,group_line)
            
            total_lst=[]
            for code in code_list:
                total_lst.append(0)
                
                
            for l_val in line.get('values'):
                r+=1
                worksheet.write(r, 1, l_val.get('employee'))
                worksheet.write(r, 2, l_val.get('department'))
                c=2
                t=0
                for line_amount in l_val.get('lines'):
                    c+=1
                    worksheet.write(r, c, line_amount,text_right)
                    total_lst[t] = total_lst[t]+ line_amount
                    t+=1
                    
            r+=1
            worksheet.write(r, 2, 'TOTAL',text_bold)
            c=2
            for total_l in total_lst:
                c+=1
                worksheet.write(r, c, total_l,text_right_bold)
            r+=1 
                    
        
                    

        fp = BytesIO()
        workbook.save(fp)
        export_id = self.env['emp.payroll.statement.excel'].create({'excel_file': base64.encodestring(fp.getvalue()), 'file_name': filename})
        fp.close()
        
        return {
            'view_mode': 'form',
            'res_id': export_id.id,
            'res_model': 'emp.payroll.statement.excel',
            'type': 'ir.actions.act_window',
            'context': self._context,
            'target': 'new',
            
        }

    def print_bank_temp(self):
        if not self.employee_ids:
            raise ValidationError(_('Please Select Employee !!!'))
            
        payslip_ids= self.get_payslip()
        if not payslip_ids:
            raise ValidationError(_('Payslip not Found !!!'))
            
        filename='CRDB Bank Template.xls'
        workbook = xlwt.Workbook()
        worksheet = workbook.add_sheet('CRDB Template')

        worksheet.write(0, 0, 'id')
        worksheet.write(0, 1, 'Name')
        worksheet.write(0, 2, 'AccountNo')
        worksheet.write(0, 3, 'Amount')
        worksheet.write(0, 4, 'bank')
        worksheet.write(0, 5, 'branch')
        worksheet.write(0, 6, 'Description')

        code_list = self.get_code_list(payslip_ids)
        line_values = self.get_lines(payslip_ids,code_list)

        net_index =  False
        for idx,code in enumerate(code_list):
            if code == 'NET':
                net_index = idx

        r=1
        for line in line_values:
            c=0
            counter =1
            for l_val in line.get('values'):
                amount = 0
                for index,line_amount in enumerate(l_val.get('lines')):
                    if index == net_index:
                        amount = line_amount

                worksheet.write(r, c,  counter)
                worksheet.write(r, c+1, l_val.get('employee'))
                worksheet.write(r, c+2, l_val.get('bank_account'))
                worksheet.write(r, c+3, amount)
                worksheet.write(r, c+4, 3)
                worksheet.write(r, c+5, 3)
                worksheet.write(r, c+6, l_val.get('description'))
                counter += 1
                r +=1

        
        fp = BytesIO()
        workbook.save(fp)
        export_id = self.env['emp.payroll.bank.excel'].create({'excel_file': base64.encodestring(fp.getvalue()), 'file_name': filename})
        fp.close()
        
        return {
            'view_mode': 'form',
            'res_id': export_id.id,
            'res_model': 'emp.payroll.bank.excel',
            'type': 'ir.actions.act_window',
            'context': self._context,
            'target': 'new',
            
        }
        
class emp_payroll_statement_excel(models.TransientModel):
    _name= "emp.payroll.statement.excel"
    excel_file = fields.Binary('Excel Report')
    file_name = fields.Char('Excel File', size=64)

class emp_payroll_bank_excel(models.TransientModel):
    _name= "emp.payroll.bank.excel"
    excel_file = fields.Binary('CRDB Template')
    file_name = fields.Char('CRDB Template', size=64)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
