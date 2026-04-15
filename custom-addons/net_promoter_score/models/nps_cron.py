from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)

class NpsCrojOB(models.Model):
    _inherit = 'net.promoter.score'
    
    @api.model
    def send_feedback_form_to_customers(self):
        customers = self.env['res.partner'].search([])
        
        # Fetch email template for feedback
        template_id = self.env.ref('net_promoter_score.email_template_customer_feedback', raise_if_not_found=False)
        if not template_id:
            _logger.warning("Email template for feedback form not found.")
            return
       
        for customer in customers:
            try:
                if customer.email:
                    _logger.info("Sending feedback form to: %s", customer.email)
                    template_id.send_mail(customer.id, force_send=True)   
            except Exception as e:
                _logger.error("Error sending email to customer %s: %s", customer.name, e)
        
        _logger.info("Feedback form emails sent to all customers.")
