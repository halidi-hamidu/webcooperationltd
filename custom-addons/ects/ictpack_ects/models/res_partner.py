from odoo import fields, models, api
import xmlrpc.client


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_ects_agent = fields.Boolean('ECTS Agent')
    is_credit_customer = fields.Boolean('ECTS Credit Customer')
    is_ects_driver = fields.Boolean("ECTS Driver")
    driver_license = fields.Char("Driver License")

    def return_ects_customers(self):
        partners = self.search([])
        values = []
        if partners:
            for rec in partners:
                value = {
                    "id": rec.id,
                    "name": rec.name,
                    "is_agent": rec.is_ects_agent,
                    "is_credit_customer": rec.is_credit_customer
                }
                values.append(value)
        return values
    
    def import_contacts(self):
        url_db16 = "http://127.0.0.1:8069"
        db_16 = 'ects'
        username_db_16 = 'admin'
        password_db_16 = '1--_ips2014-'

        common_16 = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url_db16))
        models_16 = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url_db16))
        version_db16 = common_16.version()

        url_db17 = "http://127.0.0.1:8074"
        db_17 = 'ects-aa'
        username_db_17 = 'admin'
        password_db_17 = 'admin'
        common_17 = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url_db17))
        models_17 = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url_db17))
        version_db17 = common_17.version()

        uid_db16 = common_16.authenticate(db_16, username_db_16, password_db_16, {})
        uid_db17 = common_17.authenticate(db_17, username_db_17, password_db_17, {})

        if uid_db16 and uid_db17:
            db_16_contacts = models_16.execute_kw(db_16, uid_db16, password_db_16, 'res.partner', 'search_read', [[]], {'limit': 100})
            db_17_contacts = models_17.execute_kw(db_17, uid_db17, password_db_17, 'res.partner', 'create', [db_16_contacts])

