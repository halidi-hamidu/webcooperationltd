# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    label_prefix = fields.Char(
        string='Label Prefix',
        help="Prefix for asset labels (e.g., 'FUR' for Furniture, 'ICT' for computers). "
             "Set this on the asset model, and all assets using this model will inherit the prefix.",
        size=10,
        default='IPS/'
    )
    
    asset_label = fields.Char(
        string='Asset Label',
        copy=False,
        index=True,
        help="Unique label identifier for the asset"
    )
    
    unit_number = fields.Integer(
        string='Unit Number',
        help="Unit number for assets entered in bulk (e.g., for JT701T unit 1 of 1000)"
    )
    
    total_units = fields.Integer(
        string='Total Units',
        help="Total number of units for this asset type (e.g., 1000 units of JT701T)"
    )
    
    is_bulk_entry = fields.Boolean(
        string='Bulk Entry',
        default=False,
        help="Indicates if this asset was entered as a bulk entry"
    )
    
    asset_label_ids = fields.One2many(
        'account.asset.label',
        'asset_id',
        string='Asset Labels',
        help="List of generated labels for this asset"
    )
    
    labels_count = fields.Integer(
        string='Labels Count',
        compute='_compute_labels_count',
        store=True
    )
    
    @api.depends('asset_label_ids')
    def _compute_labels_count(self):
        """Compute the number of labels."""
        for asset in self:
            asset.labels_count = len(asset.asset_label_ids)
    
    def action_view_labels(self):
        """Open the labels list view."""
        self.ensure_one()
        return {
            'name': _('Asset Labels'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.asset.label',
            'view_mode': 'tree,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id, 'create': False},
        }
    
    @api.model
    def generate_asset_label(self, prefix='IPS', padding=6):
        """
        Generate a unique asset label with the given prefix and padding.
        
        Args:
            prefix: Label prefix (default: 'IPS')
            padding: Number of digits for the sequential number (default: 6)
            
        Returns:
            str: Unique asset label (e.g., 'IPS/000001')
        """
        # Ensure prefix ends with /
        if not prefix.endswith('/'):
            prefix = prefix + '/'
        
        # Find the highest existing label number from BOTH sources
        # 1. Check in asset_label field (single labels)
        existing_assets = self.search([
            ('asset_label', '=like', f'{prefix}%')
        ], order='asset_label desc', limit=1)
        
        highest_from_assets = 0
        if existing_assets and existing_assets.asset_label:
            try:
                highest_from_assets = int(existing_assets.asset_label.split('/')[-1])
            except (ValueError, IndexError):
                highest_from_assets = 0
        
        # 2. Check in account.asset.label model (bulk labels)
        existing_labels = self.env['account.asset.label'].search([
            ('label', '=like', f'{prefix}%')
        ], order='label desc', limit=1)
        
        highest_from_labels = 0
        if existing_labels and existing_labels.label:
            try:
                highest_from_labels = int(existing_labels.label.split('/')[-1])
            except (ValueError, IndexError):
                highest_from_labels = 0
        
        # Get the highest number from both sources
        highest_number = max(highest_from_assets, highest_from_labels)
        next_number = highest_number + 1 if highest_number > 0 else 1
        
        # Format with leading zeros
        return f"{prefix}{str(next_number).zfill(padding)}"
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to auto-generate label if not provided."""
        for vals in vals_list:
            # Auto-generate label only if not provided and not a model
            if not vals.get('asset_label') and vals.get('state') != 'model':
                # Get prefix from model_id or from the record's label_prefix
                prefix = 'AST'  # Default prefix
            
            if vals.get('model_id'):
                # Get prefix from the asset model
                model = self.env['account.asset'].browse(vals['model_id'])
                if model.label_prefix:
                    prefix = model.label_prefix
            elif vals.get('label_prefix'):
                # Use the prefix set on the record itself
                prefix = vals['label_prefix']
            
            vals['asset_label'] = self.generate_asset_label(prefix=prefix)
        
        return super(AccountAsset, self).create(vals_list)
