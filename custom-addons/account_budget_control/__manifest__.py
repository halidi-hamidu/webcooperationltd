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
    'name': 'Account Budget Control',
    'version': '19.0.1.0',
    'summary': 'Budget Expenditure and Project Control',
    'description': 'Helps control expenditure and project budgets with allocation and relocation features',
    'category': 'Accounting',
    'author': 'IctPack Solutions Ltd',
    'maintainer': 'IctPack Solutions Ltd',
    'company': 'IctPack Solutions Ltd',
    'website': 'https://www.ictpack.com',
    'depends': [
     'account_budget',
     'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/account_budget_views.xml',
        'views/account_move_views.xml',
    ],
    'images': ['static/description/banner.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}
