from odoo import http
from odoo.http import request
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning

class CustomerFeedbackFormController(http.Controller):

    @http.route('/customer-feedback/form', methods=['GET', 'POST'], type='http', auth='public', website=True)
    def feedback_form(self, **kwargs):
        vals = {}
        error_list = []

        if request.httprequest.method == "POST":
            try:
                score = kwargs.get('number')
                if not score:
                    error_list.append('Rate Score Value is required.')
                else:
                    score = int(score)

                feedback_data = {
                    'name': kwargs.get('name'),
                    'email': kwargs.get('email'),
                    'feedback': kwargs.get('feedback'),
                    'score': score if score else 0,
                    'is_submitted': True,
                    'voter_identification': self.voter_idenification(score) if score else 'Unknown',
                }

                if not error_list:
                    feedback_created = request.env['net.promoter.score'].sudo().create(feedback_data)
                    if feedback_created:
                        vals['success'] = 'Thank you for your feedback!'
            except (ValueError, ValidationError) as e:
                error_list.append('Invalid input: ' + str(e))
            except Exception as e:
                error_list.append('Unexpected error occurred: ' + str(e))

        vals['error_list'] = error_list
        return request.render('net_promoter_score.feedback_form_template', vals)
    
    def voter_idenification(self, score):
        if score < 7:
            return 'Detractor'
        elif 7 <= score <= 8:
            return 'Passive'
        else:
            return 'Promoter'
