from odoo import models, fields, api


class HelpdeskTag(models.Model):
    _inherit = 'helpdesk.tag'
    
    # No custom fields - using default tag behavior
    