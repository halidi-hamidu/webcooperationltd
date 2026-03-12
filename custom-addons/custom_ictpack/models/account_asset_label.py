# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AccountAssetLabel(models.Model):
    _name = 'account.asset.label'
    _description = 'Asset Label'
    _order = 'label_number'

    asset_id = fields.Many2one(
        'account.asset',
        string='Asset',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    label = fields.Char(
        string='Label',
        required=True,
        index=True,
        help="Generated label identifier"
    )
    
    label_number = fields.Integer(
        string='Label Number',
        help="Sequential number for this label"
    )
    
    _label_unique = models.Constraint('unique(label)', 'Label must be unique!')
