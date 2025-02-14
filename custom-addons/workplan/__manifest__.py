# -*- coding: utf-8 -*-
#############################################################################
#
#    IctPack Solutions Ltd.
#
#    Copyright (C) 2022-TODAY IctPack Solutions Ltd
#    Author: IctPack Solutions Ltd
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
{
    'name': 'Workplan',
    'version': '16.0.1.0.0',
    'summary': 'Software tool that has been developed to assist facilitate monitoring and evaluation of workplan',
    'description': 'Software tool that has been developed to assist facilitate monitoring and evaluation of workplan',
    'category': 'Extra Tools',
    'author': 'IctPack Solutions Ltd',
    'maintainer': 'IctPack Solutions Ltd',
    'company': 'IctPack Solutions Ltd',
    'website': 'https://www.ictpack.com',
    'depends': ['base', 'mail','hr','project','uom','account_budget_control'],
    'data': [
        'security/workplan_security.xml',
        'security/ir.model.access.csv',
        'views/workplan_menu_views.xml',
        'views/res_obj_out_indicator_views.xml',
        'views/workplan_views.xml',
        'views/hr_department_views.xml',
        'views/project_views.xml',
        'views/account_budget_views.xml',
        'views/workplan_fields_config_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}
