from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
# from odoo import http

RESET_PASSWORD_TEMPLATE = 'ictpack_vts.reset_password_template'

class ResetPasswordController(http.Controller):

    @http.route('/reset_password', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def reset_password(self, **kwargs):
        token = kwargs.get('token')
        new_password = kwargs.get('new_password')

        if request.httprequest.method == 'POST':
            if not token or not new_password:
                return request.render(RESET_PASSWORD_TEMPLATE)

            try:
                # Call the reset_password method
                request.env['hr.employee'].sudo().reset_password({
                    'token': token,
                    'new_password': new_password
                })
                return request.render('ictpack_vts.reset_password_success')
            except Exception as e:
                return request.render(RESET_PASSWORD_TEMPLATE, {'error': str(e)})
        
        return request.render(RESET_PASSWORD_TEMPLATE, {'token': token})

# class VtsJobCardController(http.Controller):

#     @http.route('/my/jobcards', type='http', auth='user', website=True)
#     def portal_my_jobcards(self, **kw):
#         jobcards = request.env['vts.job.card'].search([('vts_employee.user_id', '=', request.env.user.id)])
#         return request.render('ictpack_vts.portal_my_jobcards', {
#             'jobcards': jobcards,
#         })

#     @http.route('/my/jobcard/<int:jobcard_id>', type='http', auth='user', website=True)
#     def portal_my_jobcard(self, jobcard_id, **kw):
#         jobcard = request.env['vts.job.card'].browse(jobcard_id)
#         return request.render('ictpack_vts.portal_my_jobcard', {
#             'jobcard': jobcard,
#         })