# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015 DevIntelle Consulting Service Pvt.Ltd (<http://www.devintellecs.com>).
#
#    For Module Support : devintelle@gmail.com  or Skype : devintelle 
#
##############################################################################

from odoo import models, fields, api, _
from datetime import datetime
import dateutil.relativedelta
from datetime import timedelta
import calendar
from odoo.tools.misc import formatLang

class print_customer_statement(models.AbstractModel): 
    _name = 'report.dev_customer_statement_advance.dev_acc_statement_temp'
    
    def get_company_info(self,o):
        if self.env.user.company_id:
            compnay_info = {
                    'image':self.env.user.company_id or False,
                    'name':self.env.user.company_id.name or False,
                    'street':self.env.user.company_id.street or False,
                    'city':str(self.env.user.company_id.city) +' '+str(self.env.user.company_id.zip) or False,
                    'state':self.env.user.company_id.state_id and self.env.user.company_id.state_id.name or False,
                    'country':self.env.user.company_id.country_id and self.env.user.company_id.country_id.name or False ,
            }
        return compnay_info
    
    def set_amount(self, amount):
        amount  = formatLang(self.env, amount)
        return amount


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

    def set_ageing(self,obj):
        over_date=obj.overdue_date
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
        for line in obj.statement_lines:
            ag_date=False
            if obj.aging_by == 'due_date':
                ag_date = line.due_date
            else:
                ag_date = line.invoice_date
            if ag_date and obj.overdue_date:
                due_date=ag_date
                over_date=obj.overdue_date
                if over_date != due_date:
                    if not ag_date > obj.overdue_date: 
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
    
    
    def set_ageing_date(self,obj):
        over_date=obj.overdue_date
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
        for line in obj.statement_lines:
            ag_date=False
            if obj.aging_by == 'due_date':
                ag_date = line.due_date
            else:
                ag_date = line.invoice_date
            if ag_date and obj.overdue_date:
                due_date=ag_date
                over_date=obj.overdue_date
                if over_date != due_date:
                    if not ag_date > obj.overdue_date: 
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
            

    @api.model
    def _get_report_values(self, docids, data=None):
        if data.get('form'):
            docs = self.env['res.partner'].browse(data['form'])
        else:
            docs = self.env['res.partner'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'res.partner',
            'docs': docs,
            'set_ageing':self.set_ageing,
            'set_ageing_date':self.set_ageing_date,
            'set_amount':self.set_amount,
            'get_company_info':self.get_company_info,
        }

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
