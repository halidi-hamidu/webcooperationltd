{
    'name': 'Multiple Payslip',
    'version': "16.0.1.0.0",
    'author': 'Aktiv Software',
    'website': 'http://www.aktivsoftware.com',
    'summary': 'Create Multiple Payslip at a same time.',
    'category': 'Generic Modules/Human Resources',
    'license': '',
    'depends': ['hr','hr_payroll'],
    'data': [
            'wizard/mutli_payslip_view.xml',
            'wizard/multi_payslip_confirm.xml',
    ],
    'description': """
        This Module is For create Multiple Payslip at the same
        time...
    """,

    'images': ['static/description/banner.jpg'],
    'auto_install': False,
    'installable': True,
}
