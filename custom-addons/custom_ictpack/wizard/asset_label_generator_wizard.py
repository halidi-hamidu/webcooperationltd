# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import re


class AssetLabelGeneratorWizard(models.TransientModel):
    _name = 'asset.label.generator.wizard'
    _description = 'Asset Label Generator Wizard'

    asset_id = fields.Many2one(
        'account.asset',
        string='Asset',
        required=True,
        readonly=True,
        default=lambda self: self._default_asset_id()
    )
    
    generation_mode = fields.Selection([
        ('single', 'Generate Single Label'),
        ('bulk', 'Generate Labels for Bulk Entry')
    ], string='Generation Mode', default='single', required=True)
    
    # Single label generation
    label_prefix = fields.Char(
        string='Label Prefix',
        compute='_compute_label_prefix',
        store=True,
        readonly=False,
        help="Prefix for the asset label (e.g., 'AST', 'ICT', 'FUR')"
    )
    
    @api.model
    def _default_asset_id(self):
        """Get asset_id from context."""
        return self.env.context.get('active_id', False)
    
    custom_label = fields.Char(
        string='Custom Label',
        help="Enter a custom label or leave blank for auto-generation"
    )
    
    # Bulk label generation
    start_unit = fields.Integer(
        string='Start Unit Number',
        default=1,
        help="Starting unit number for bulk generation"
    )
    
    end_unit = fields.Integer(
        string='End Unit Number',
        default=1,
        help="Ending unit number for bulk generation"
    )
    
    bulk_label_format = fields.Selection([
        ('sequential', 'Sequential (IPS/FU/000001, IPS/FU/000002, ...)'),
        ('with_unit', 'With Unit Number (JT701T-U001, JT701T-U002, ...)'),
        ('custom', 'Custom Format')
    ], string='Label Format', default='sequential')
    
    custom_format = fields.Char(
        string='Custom Format',
        help="Use {name} for asset name, {unit} for unit number. E.g., '{name}-U{unit:03d}'"
    )
    
    preview_labels = fields.Text(
        string='Label Preview',
        compute='_compute_preview_labels',
        readonly=True
    )
    
    total_labels_count = fields.Integer(
        string='Total Labels',
        compute='_compute_preview_labels',
        readonly=True
    )
    
    @api.depends('asset_id')
    def _compute_label_prefix(self):
        """Set prefix from asset's model."""
        for wizard in self:
            if wizard.asset_id:
                # Get prefix from the asset's model
                if wizard.asset_id.model_id and wizard.asset_id.model_id.label_prefix:
                    wizard.label_prefix = wizard.asset_id.model_id.label_prefix
                elif wizard.asset_id.label_prefix:
                    # Or from the asset itself if it's set
                    wizard.label_prefix = wizard.asset_id.label_prefix
                else:
                    # Default fallback
                    wizard.label_prefix = 'AST'
            else:
                wizard.label_prefix = 'AST'
    
    @api.depends('generation_mode', 'start_unit', 'end_unit', 'bulk_label_format', 
                 'custom_format', 'label_prefix', 'asset_id', 'custom_label')
    def _compute_preview_labels(self):
        """Compute preview of labels to be generated."""
        for wizard in self:
            if wizard.generation_mode == 'single':
                if wizard.custom_label:
                    wizard.preview_labels = wizard.custom_label
                else:
                    prefix = wizard.label_prefix if wizard.label_prefix.endswith('/') else wizard.label_prefix + '/'
                    wizard.preview_labels = f"{prefix}XXXXXX (auto-generated)"
                wizard.total_labels_count = 1
            else:
                # Bulk generation preview
                if wizard.start_unit > wizard.end_unit:
                    wizard.preview_labels = "Error: Start unit must be less than or equal to end unit"
                    wizard.total_labels_count = 0
                    continue
                
                count = wizard.end_unit - wizard.start_unit + 1
                wizard.total_labels_count = count
                
                # Generate preview (first 5 and last 2 if more than 7)
                preview_list = []
                if wizard.bulk_label_format == 'sequential':
                    # Ensure prefix ends with /
                    prefix = wizard.label_prefix if wizard.label_prefix.endswith('/') else wizard.label_prefix + '/'
                    
                    # Find the highest number from BOTH sources
                    # 1. Check asset_label field
                    last_asset = self.env['account.asset'].search([
                        ('asset_label', '=like', f'{prefix}%')
                    ], order='asset_label desc', limit=1)
                    
                    highest_from_assets = 0
                    if last_asset and last_asset.asset_label:
                        try:
                            highest_from_assets = int(last_asset.asset_label.split('/')[-1])
                        except (ValueError, IndexError):
                            highest_from_assets = 0
                    
                    # 2. Check account.asset.label model
                    last_label = self.env['account.asset.label'].search([
                        ('label', '=like', f'{prefix}%')
                    ], order='label desc', limit=1)
                    
                    highest_from_labels = 0
                    if last_label and last_label.label:
                        try:
                            highest_from_labels = int(last_label.label.split('/')[-1])
                        except (ValueError, IndexError):
                            highest_from_labels = 0
                    
                    # Get the highest from both
                    highest_number = max(highest_from_assets, highest_from_labels)
                    start_num = highest_number + 1 if highest_number > 0 else 1
                    
                    for i in range(min(5, count)):
                        preview_list.append(f"{prefix}{str(start_num + i).zfill(6)}")
                    
                    if count > 7:
                        preview_list.append("...")
                        for i in range(count - 2, count):
                            preview_list.append(f"{prefix}{str(start_num + i).zfill(6)}")
                    elif count > 5:
                        for i in range(5, count):
                            preview_list.append(f"{prefix}{str(start_num + i).zfill(6)}")
                
                elif wizard.bulk_label_format == 'with_unit':
                    asset_name = wizard.asset_id.name or 'ASSET'
                    # Clean asset name for use in label
                    clean_name = re.sub(r'[^A-Za-z0-9-]', '', asset_name.replace(' ', ''))[:20]
                    
                    for i in range(min(5, count)):
                        unit_num = wizard.start_unit + i
                        preview_list.append(f"{clean_name}-U{str(unit_num).zfill(3)}")
                    
                    if count > 7:
                        preview_list.append("...")
                        for i in range(count - 2, count):
                            unit_num = wizard.start_unit + i
                            preview_list.append(f"{clean_name}-U{str(unit_num).zfill(3)}")
                    elif count > 5:
                        for i in range(5, count):
                            unit_num = wizard.start_unit + i
                            preview_list.append(f"{clean_name}-U{str(unit_num).zfill(3)}")
                
                elif wizard.bulk_label_format == 'custom' and wizard.custom_format:
                    try:
                        for i in range(min(5, count)):
                            unit_num = wizard.start_unit + i
                            label = wizard.custom_format.format(
                                name=wizard.asset_id.name or 'ASSET',
                                unit=unit_num
                            )
                            preview_list.append(label)
                        
                        if count > 7:
                            preview_list.append("...")
                            for i in range(count - 2, count):
                                unit_num = wizard.start_unit + i
                                label = wizard.custom_format.format(
                                    name=wizard.asset_id.name or 'ASSET',
                                    unit=unit_num
                                )
                                preview_list.append(label)
                        elif count > 5:
                            for i in range(5, count):
                                unit_num = wizard.start_unit + i
                                label = wizard.custom_format.format(
                                    name=wizard.asset_id.name or 'ASSET',
                                    unit=unit_num
                                )
                                preview_list.append(label)
                    except Exception as e:
                        preview_list = [f"Error in format: {str(e)}"]
                else:
                    preview_list = ["Select a label format"]
                
                wizard.preview_labels = "\n".join(preview_list)
    
    @api.constrains('start_unit', 'end_unit')
    def _check_unit_range(self):
        """Validate unit range."""
        for wizard in self:
            if wizard.generation_mode == 'bulk':
                if wizard.start_unit < 1:
                    raise ValidationError(_("Start unit must be at least 1."))
                if wizard.end_unit < wizard.start_unit:
                    raise ValidationError(_("End unit must be greater than or equal to start unit."))
                if (wizard.end_unit - wizard.start_unit + 1) > 10000:
                    raise ValidationError(_("Cannot generate more than 10,000 labels at once. Please split into smaller batches."))
    
    def action_generate_labels(self):
        """Generate labels based on the selected mode."""
        self.ensure_one()
        
        if self.generation_mode == 'single':
            return self._generate_single_label()
        else:
            return self._generate_bulk_labels()
    
    def _generate_single_label(self):
        """Generate a single label for the asset."""
        if self.custom_label:
            # Check if label already exists
            existing = self.env['account.asset'].search([
                ('asset_label', '=', self.custom_label),
                ('id', '!=', self.asset_id.id)
            ], limit=1)
            
            if existing:
                raise UserError(_(
                    "Label '%s' already exists for asset '%s'. Please choose a different label."
                ) % (self.custom_label, existing.name))
            
            label = self.custom_label
        else:
            # Auto-generate label
            label = self.asset_id.generate_asset_label(prefix=self.label_prefix)
        
        # Update the asset
        self.asset_id.write({
            'asset_label': label,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Label %s generated successfully!') % label,
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _generate_bulk_labels(self):
        """Generate labels for bulk assets."""
        self.ensure_one()
        
        # Generate labels and add to current asset
        count = self.end_unit - self.start_unit + 1
        
        if count > 10000:
            raise UserError(_(
                "Cannot generate more than 10,000 labels at once. Please split into smaller batches."
            ))
        
        original_asset = self.asset_id
        
        # Mark as bulk entry
        original_asset.write({
            'is_bulk_entry': True,
            'total_units': count,
        })
        
        # Delete existing labels if any (to allow regeneration)
        original_asset.asset_label_ids.unlink()
        
        # For sequential format, get the starting number once
        start_sequential_num = None
        if self.bulk_label_format == 'sequential':
            # Ensure prefix ends with /
            prefix = self.label_prefix if self.label_prefix.endswith('/') else self.label_prefix + '/'
            
            # Find the highest number from BOTH sources
            # Check asset_label field
            last_asset = self.env['account.asset'].search([
                ('asset_label', '=like', f'{prefix}%')
            ], order='asset_label desc', limit=1)
            
            highest_from_assets = 0
            if last_asset and last_asset.asset_label:
                try:
                    highest_from_assets = int(last_asset.asset_label.split('/')[-1])
                except (ValueError, IndexError):
                    highest_from_assets = 0
            
            # Check account.asset.label model
            last_label = self.env['account.asset.label'].search([
                ('label', '=like', f'{prefix}%')
            ], order='label desc', limit=1)
            
            highest_from_labels = 0
            if last_label and last_label.label:
                try:
                    highest_from_labels = int(last_label.label.split('/')[-1])
                except (ValueError, IndexError):
                    highest_from_labels = 0
            
            # Get the highest from both
            highest_number = max(highest_from_assets, highest_from_labels)
            start_sequential_num = highest_number + 1 if highest_number > 0 else 1
        
        # Generate labels
        label_vals_list = []
        for i in range(count):
            unit_num = self.start_unit + i
            
            # Generate label based on format
            if self.bulk_label_format == 'sequential':
                # Ensure prefix ends with /
                prefix = self.label_prefix if self.label_prefix.endswith('/') else self.label_prefix + '/'
                label = f"{prefix}{str(start_sequential_num + i).zfill(6)}"
            elif self.bulk_label_format == 'with_unit':
                clean_name = re.sub(r'[^A-Za-z0-9-]', '', original_asset.name.replace(' ', ''))[:20]
                label = f"{clean_name}-U{str(unit_num).zfill(3)}"
            elif self.bulk_label_format == 'custom' and self.custom_format:
                try:
                    label = self.custom_format.format(
                        name=original_asset.name,
                        unit=unit_num
                    )
                except Exception as e:
                    raise UserError(_("Error in custom format: %s") % str(e))
            else:
                label = original_asset.generate_asset_label(prefix=self.label_prefix)
            
            # Check for duplicate label in other assets
            existing = self.env['account.asset.label'].search([
                ('label', '=', label),
                ('asset_id', '!=', original_asset.id)
            ], limit=1)
            
            if existing:
                raise UserError(_("Label '%s' already exists on another asset. Please adjust your format or range.") % label)
            
            label_vals_list.append({
                'asset_id': original_asset.id,
                'label': label,
                'label_number': unit_num,
            })
        
        # Create all labels
        self.env['account.asset.label'].create(label_vals_list)
        
        # Update the main asset label to show first label
        if label_vals_list:
            original_asset.write({
                'asset_label': label_vals_list[0]['label'],
            })
        
        # Return action to show the asset with labels
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%d labels generated successfully!') % count,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.asset',
                    'res_id': original_asset.id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            }
        }
