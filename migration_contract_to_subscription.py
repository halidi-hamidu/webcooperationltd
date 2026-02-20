#!/usr/bin/env python3
"""
Migration Script: Odoo 16 Contract Module -> Odoo 19 Subscription Module
Uses JSON-RPC to migrate contract data between instances.

Usage:
    python migration_contract_to_subscription.py
"""

import logging
import sys
from typing import Any, Dict, List, Optional

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OdooJSONRPC:
    """JSON-RPC client for Odoo"""
    
    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self.session_id = None
        self.session = requests.Session()  # Use session to maintain cookies
        
    def authenticate(self) -> bool:
        """Authenticate and get UID"""
        try:
            headers = {'Content-Type': 'application/json'}
            payload = {
                'jsonrpc': '2.0',
                'method': 'call',
                'params': {
                    'db': self.db,
                    'login': self.username,
                    'password': self.password
                },
                'id': 1
            }
            
            response = self.session.post(
                f"{self.url}/web/session/authenticate",
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                logger.error(f"✗ Authentication failed: {result['error']}")
                return False
            
            result_data = result.get('result', {})
            if result_data and result_data.get('uid'):
                self.uid = result_data['uid']
                self.session_id = result_data.get('session_id')
                logger.info(f"✓ Authentication successful for {self.username} (UID: {self.uid})")
                return True
            logger.error("✗ Authentication failed: No UID returned")
            return False
        except Exception as e:
            logger.error(f"✗ Authentication error: {e}")
            return False
    
    def call(self, endpoint: str, params: Dict) -> Any:
        """Make JSON-RPC call using authenticated session"""
        self.last_error = None
        headers = {'Content-Type': 'application/json'}
        payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': params,
            'id': 1
        }
        
        try:
            response = self.session.post(
                f"{self.url}{endpoint}",
                json=payload,
                headers=headers,
                timeout=300
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                error_data = result['error']
                # Check for session expiration
                if 'Session' in str(error_data.get('message', '')):
                    logger.warning("Session expired, re-authenticating...")
                    if self.authenticate():
                        # Retry the call
                        return self.call(endpoint, params)
                # Extract meaningful error message
                error_msg = error_data.get('data', {}).get('message', '') or error_data.get('message', '')
                self.last_error = error_msg
                logger.debug(f"RPC Error: {error_msg}")
                return None
            
            return result.get('result')
        except requests.exceptions.RequestException as e:
            self.last_error = str(e)
            logger.error(f"Request error: {e}")
            return None
    
    def execute_kw(self, model: str, method: str, args: List, kwargs: Optional[Dict] = None) -> Any:
        """Execute ORM method"""
        if not self.uid:
            logger.error("Not authenticated")
            return None
        
        params = {
            'model': model,
            'method': method,
            'args': args,
            'kwargs': kwargs or {}
        }
        
        return self.call('/web/dataset/call_kw', params)
    
    def search_read(self, model: str, domain: List, fields: List, limit: Optional[int] = None) -> List[Dict]:
        """Search and read records"""
        kwargs = {'fields': fields}
        if limit:
            kwargs['limit'] = limit
        
        return self.execute_kw(model, 'search_read', [domain], kwargs) or []
    
    def create(self, model: str, values: Dict) -> Optional[int]:
        """Create a record"""
        result = self.execute_kw(model, 'create', [[values]])
        if isinstance(result, int):
            return result
        # Odoo 17+ returns a list of IDs from create([vals])
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], int):
            return result[0]
        return None
    
    def write(self, model: str, record_id: int, values: Dict) -> bool:
        """Update a record"""
        result = self.execute_kw(model, 'write', [[record_id], values])
        return bool(result)


class ContractToSubscriptionMigration:
    """Migrate contracts from Odoo 16 to subscriptions in Odoo 19"""
    
    # Field mapping: Contract (v16) -> Sale Order (Subscription) (v19)
    # Note: partner_id, invoice_partner_id, pricelist_id handled separately
    # Note: tag_ids skipped (contract.tag vs sale.order tags are different models)
    # Note: currency_id skipped (computed from pricelist on sale.order)
    CONTRACT_FIELD_MAP = {
        'payment_term_id': 'payment_term_id',
        'fiscal_position_id': 'fiscal_position_id',
        'user_id': 'user_id',
        'company_id': 'company_id',
        'date_start': 'start_date',
        'date_end': 'end_date',
        'code': 'client_order_ref',
        'note': 'note',
        'business_line': 'business_line',       # custom field (custom_ictpack)
        'journal_id': 'journal_id',
        'recurring_next_date': 'next_invoice_date',
    }
    
    # Note: recurring_invoice is a related/computed field on sale.order.line, cannot be set directly
    LINE_FIELD_MAP = {
        'name': 'name',
        'product_id': 'product_id',
        'quantity': 'product_uom_qty',
        'price_unit': 'price_unit',
        'discount': 'discount',
        'uom_id': 'product_uom_id',
        'sequence': 'sequence',
    }
    
    # Recurrency mapping: contract recurring_rule_type -> subscription plan billing_period_unit
    # Subscription plans only support: week, month, year
    RECURRING_RULE_TYPE_MAP = {
        'daily': 'week',            # No 'day' in subscription plans, fallback to week
        'weekly': 'week',
        'monthly': 'month',
        'monthlylastday': 'month',
        'quarterly': 'month',       # 3 months (interval adjusted in code)
        'semesterly': 'month',      # 6 months (interval adjusted in code)
        'yearly': 'year',
    }
    
    def __init__(self, source: OdooJSONRPC, target: OdooJSONRPC):
        self.source = source
        self.target = target
        self.stats = {
            'contracts_processed': 0,
            'contracts_migrated': 0,
            'contracts_failed': 0,
            'contracts_skipped_no_partner': 0,
            'lines_migrated': 0,
            'lines_skipped_no_product': 0,
            'errors': []
        }
        # Mapping of old IDs to new IDs
        self.partner_map = {}
        self.product_map = {}
        self.pricelist_map = {}
        self.contract_map = {}
        # Default product for atras lines without product (PD032)
        self.atras_default_product_id = None
        # TZS pricelist for atras contracts
        self.atras_pricelist_id = None
        
    def migrate(self, domain: Optional[List] = None, limit: Optional[int] = None):
        """Main migration process"""
        logger.info("=" * 60)
        logger.info("Starting Contract to Subscription Migration")
        logger.info("=" * 60)
        
        # Authenticate both instances
        if not self.source.authenticate():
            logger.error("Failed to authenticate source instance")
            return False
        
        if not self.target.authenticate():
            logger.error("Failed to authenticate target instance")
            return False
        
        # Build partner and product mappings
        self._build_mappings()
        
        # Get contracts from source
        contract_domain = domain or [('active', 'in', [True, False])]
        contracts = self.source.search_read(
            'contract.contract',
            contract_domain,
            [
                'name', 'code', 'active', 'partner_id', 'date_start', 'date_end',
                'pricelist_id', 'journal_id', 'payment_term_id', 'fiscal_position_id',
                'user_id', 'company_id', 'recurring_rule_type', 'recurring_interval',
                'recurring_next_date', 'contract_type', 'invoice_partner_id',
                'contract_line_ids', 'note', 'business_line', 'currency_id',
                'is_terminated',
            ],
            limit=limit
        )
        
        logger.info(f"Found {len(contracts)} contracts to migrate")
        
        # Migrate each contract
        for contract in contracts:
            self._migrate_contract(contract)
        
        # Print statistics
        self._print_statistics()
        
        return True
    
    def _build_mappings(self):
        """Build mappings for partners and products between instances"""
        logger.info("Building partner and product mappings...")
        
        # Map partners by name, phone, and email
        source_partners = self.source.search_read(
            'res.partner',
            [],
            ['name', 'email', 'phone', 'ref']
        )
        
        for partner in source_partners:
            # Try to find matching partner in target using multiple strategies
            target_partners = None
            
            # Strategy 1: Match by name + phone (most reliable)
            if partner.get('name') and partner.get('phone'):
                target_domain = [
                    ('name', '=', partner['name']),
                    ('phone', '=', partner['phone'])
                ]
                target_partners = self.target.search_read('res.partner', target_domain, ['id'], limit=1)
            
            # Strategy 2: Match by email (if unique and exists)
            if not target_partners and partner.get('email'):
                target_domain = [('email', '=', partner['email'])]
                target_partners = self.target.search_read('res.partner', target_domain, ['id'], limit=1)
            
            # Strategy 3: Match by reference code
            if not target_partners and partner.get('ref'):
                target_domain = [('ref', '=', partner['ref'])]
                target_partners = self.target.search_read('res.partner', target_domain, ['id'], limit=1)
            
            if target_partners:
                self.partner_map[partner['id']] = target_partners[0]['id']
        
        logger.info(f"Mapped {len(self.partner_map)} partners (unmatched partners will be skipped)")
        
        # Map products by default_code or name
        source_products = self.source.search_read(
            'product.product',
            [],
            ['name', 'default_code']
        )
        
        for product in source_products:
            target_domain = []
            if product.get('default_code'):
                target_domain = [('default_code', '=', product['default_code'])]
            else:
                target_domain = [('name', '=', product['name'])]
            
            target_products = self.target.search_read('product.product', target_domain, ['id'], limit=1)
            if target_products:
                self.product_map[product['id']] = target_products[0]['id']
        
        logger.info(f"Mapped {len(self.product_map)} products")
        
        # Map pricelists by name and currency
        source_pricelists = self.source.search_read(
            'product.pricelist',
            [],
            ['name', 'currency_id']
        )
        
        for pricelist in source_pricelists:
            target_domain = [('name', '=', pricelist['name'])]
            if pricelist.get('currency_id'):
                currency_name = pricelist['currency_id'][1] if isinstance(pricelist['currency_id'], list) else None
                if currency_name:
                    # Find currency in target
                    currencies = self.target.search_read(
                        'res.currency',
                        [('name', '=', currency_name.split()[0])],  # Extract currency code like 'USD' from 'USD Pricelist (USD)'
                        ['id'],
                        limit=1
                    )
                    if currencies:
                        target_domain.append(('currency_id', '=', currencies[0]['id']))
            
            target_pricelists = self.target.search_read('product.pricelist', target_domain, ['id'], limit=1)
            if target_pricelists:
                self.pricelist_map[pricelist['id']] = target_pricelists[0]['id']
        
        logger.info(f"Mapped {len(self.pricelist_map)} pricelists")
        
        # Resolve default atras product (PD032 - ATRAS Service Charges)
        atras_products = self.target.search_read(
            'product.product',
            [('default_code', '=', 'PD032')],
            ['id'],
            limit=1
        )
        if atras_products:
            self.atras_default_product_id = atras_products[0]['id']
            logger.info(f"Resolved atras default product PD032 (ID: {self.atras_default_product_id})")
        else:
            logger.warning("⚠ Default atras product PD032 not found in target!")
        
        # Resolve TZS pricelist for atras contracts
        tzs_pricelists = self.target.search_read(
            'product.pricelist',
            [('name', 'ilike', 'TZS')],
            ['id', 'name'],
            limit=1
        )
        if tzs_pricelists:
            self.atras_pricelist_id = tzs_pricelists[0]['id']
            logger.info(f"Resolved atras TZS pricelist: {tzs_pricelists[0]['name']} (ID: {self.atras_pricelist_id})")
        else:
            logger.warning("⚠ TZS pricelist not found in target for atras contracts!")
    
    def _migrate_contract(self, contract: Dict):
        """Migrate a single contract to subscription"""
        self.stats['contracts_processed'] += 1
        contract_name = contract.get('name', 'Unknown')
        
        try:
            logger.info(f"\n[{self.stats['contracts_processed']}] Migrating: {contract_name}")
            
            # Map partner (must exist in target)
            partner_id = self._map_partner(contract.get('partner_id'))
            if not partner_id:
                self.stats['contracts_skipped_no_partner'] += 1
                logger.warning(f"  ⚠ Skipping contract: partner not found in target: {contract.get('partner_id')}")
                return
            
            # Prepare subscription data
            order_vals = self._prepare_subscription_values(contract, partner_id)
            
            # Create sale order (subscription)
            order_id = self.target.create('sale.order', order_vals)
            if not order_id:
                raise ValueError(f"Failed to create sale order: {self.target.last_error}")
            
            logger.info(f"  ✓ Created sale order (subscription) ID: {order_id}")
            self.contract_map[contract['id']] = order_id
            
            # Migrate contract lines
            if contract.get('contract_line_ids'):
                self._migrate_contract_lines(
                    contract['contract_line_ids'], order_id,
                    business_line=contract.get('business_line')
                )
            
            self.stats['contracts_migrated'] += 1
            logger.info(f"  ✓ Successfully migrated contract: {contract_name}")
            
        except Exception as e:
            self.stats['contracts_failed'] += 1
            error_msg = f"Failed to migrate contract '{contract_name}': {str(e)}"
            logger.error(f"  ✗ {error_msg}")
            self.stats['errors'].append(error_msg)
    
    def _prepare_subscription_values(self, contract: Dict, partner_id: int) -> Dict:
        """Prepare sale order values with subscription data"""
        vals = {
            'partner_id': partner_id,
            # is_subscription is computed from plan_id, don't set it directly
        }
        
        # Map basic fields
        for source_field, target_field in self.CONTRACT_FIELD_MAP.items():
            
            value = contract.get(source_field)
            if value is not False and value is not None:
                # Handle Many2one fields (returned as [id, name])
                if isinstance(value, list) and len(value) >= 2:
                    vals[target_field] = value[0]
                elif value:
                    vals[target_field] = value
        
        # Handle pricelist (needs mapping)
        # For atras contracts, force TZS pricelist
        if contract.get('business_line') == 'atras' and self.atras_pricelist_id:
            vals['pricelist_id'] = self.atras_pricelist_id
        elif contract.get('pricelist_id'):
            pricelist_id = contract['pricelist_id'][0] if isinstance(contract['pricelist_id'], list) else contract['pricelist_id']
            if pricelist_id in self.pricelist_map:
                vals['pricelist_id'] = self.pricelist_map[pricelist_id]
            else:
                logger.warning(f"  ⚠ Pricelist {pricelist_id} not found in target, skipping")
        
        # Handle recurrence
        if contract.get('recurring_rule_type'):
            rule_type = contract['recurring_rule_type']
            interval = contract.get('recurring_interval', 1)
            plan_unit = self.RECURRING_RULE_TYPE_MAP.get(rule_type, 'month')
            # Adjust interval for quarterly (3 months) and semesterly (6 months)
            if rule_type == 'quarterly':
                interval = interval * 3
            elif rule_type == 'semesterly':
                interval = interval * 6
            vals['plan_id'] = self._get_or_create_recurrence_plan(plan_unit, interval)
        
        # Handle invoice partner (needs mapping)
        if contract.get('invoice_partner_id'):
            invoice_partner = self._map_partner(contract['invoice_partner_id'])
            if invoice_partner:
                vals['partner_invoice_id'] = invoice_partner
        
        # Handle contract type (sale/purchase)
        if contract.get('contract_type') == 'purchase':
            vals['client_order_ref'] = f"[PURCHASE] {vals.get('client_order_ref', '')}"
        
        return vals
    
    def _migrate_contract_lines(self, line_ids: List[int], order_id: int, business_line: str = None):
        """Migrate contract lines to sale order lines"""
        # Get contract lines
        lines = self.source.search_read(
            'contract.line',
            [('id', 'in', line_ids)],
            [
                'name', 'product_id', 'quantity', 'price_unit', 'discount',
                'uom_id', 'date_start', 'date_end', 'sequence',
                'recurring_rule_type', 'recurring_interval', 'display_type',
                'is_canceled',
            ]
        )
        
        logger.info(f"  Migrating {len(lines)} contract lines...")
        
        for line in lines:
            try:
                # Handle section/note lines
                if line.get('display_type') in ['line_section', 'line_note']:
                    line_vals = {
                        'order_id': order_id,
                        'display_type': line['display_type'],
                        'name': line.get('name', ''),
                        'sequence': line.get('sequence', 10),
                    }
                else:
                    # Map product if it exists
                    product_id = self._map_product(line.get('product_id'))
                    
                    line_vals = {
                        'order_id': order_id,
                    }
                    
                    # Map all line fields
                    for source_field, target_field in self.LINE_FIELD_MAP.items():
                        value = line.get(source_field)
                        if value is not False and value is not None:
                            if isinstance(value, list) and len(value) >= 2:
                                line_vals[target_field] = value[0]
                            elif value is not None:
                                line_vals[target_field] = value
                    
                    if product_id:
                        # Product found in target, use it
                        line_vals['product_id'] = product_id
                    elif business_line == 'atras' and self.atras_default_product_id:
                        # Atras contract — fallback to default PD032 product, keep description
                        line_vals['product_id'] = self.atras_default_product_id
                        line_vals['name'] = line.get('name') or 'ATRAS Service Charges'
                        self.stats['lines_skipped_no_product'] += 1
                        logger.info(f"    ℹ Atras line using PD032 default: {line.get('name', '')[:60]}")
                    else:
                        # No product match — create line with description only
                        line_vals.pop('product_id', None)
                        line_vals['name'] = line.get('name') or 'N/A'
                        self.stats['lines_skipped_no_product'] += 1
                        logger.info(f"    ℹ Line without product, using description: {line.get('name', '')[:60]}")
                    
                    # Set defaults if not present
                    if 'product_uom_qty' not in line_vals:
                        line_vals['product_uom_qty'] = 1.0
                    if 'sequence' not in line_vals:
                        line_vals['sequence'] = 10
                
                # Create sale order line
                line_id = self.target.create('sale.order.line', line_vals)
                if line_id:
                    self.stats['lines_migrated'] += 1
                else:
                    logger.warning(f"    ⚠ Failed to create line: {line.get('name')}")
                    
            except Exception as e:
                logger.error(f"    ✗ Error migrating line '{line.get('name')}': {e}")
    
    def _map_partner(self, partner_value) -> Optional[int]:
        """Map partner from source to target (must already exist in target)"""
        if not partner_value:
            return None
        
        partner_id = partner_value[0] if isinstance(partner_value, list) else partner_value
        
        # Check if already mapped
        if partner_id in self.partner_map:
            return self.partner_map[partner_id]
        
        return None
    
    def _map_product(self, product_value) -> Optional[int]:
        """Map product from source to target (must already exist in target)"""
        if not product_value:
            return None
        
        product_id = product_value[0] if isinstance(product_value, list) else product_value
        
        # Check if already mapped
        if product_id in self.product_map:
            return self.product_map[product_id]
        
        return None
    
    def _get_or_create_recurrence_plan(self, unit: str, interval: int) -> Optional[int]:
        """Get or create a recurrence plan (recurring plan)"""
        try:
            # Search for existing recurrence plan
            plans = self.target.search_read(
                'sale.subscription.plan',
                [('billing_period_unit', '=', unit), ('billing_period_value', '=', interval)],
                ['id'],
                limit=1
            )
            
            if plans:
                return plans[0]['id']
            
            # Create if not found
            plan_name = f"{interval} {unit.capitalize()}" if interval > 1 else unit.capitalize()
            plan_vals = {
                'name': plan_name,
                'billing_period_value': interval,
                'billing_period_unit': unit,
            }
            
            plan_id = self.target.create('sale.subscription.plan', plan_vals)
            if plan_id:
                logger.info(f"    ✓ Created recurrence plan: {plan_name} (ID: {plan_id})")
                return plan_id
                
        except Exception as e:
            logger.warning(f"    ⚠ Error with recurrence plan: {e}")
            # Try to get default monthly plan as fallback
            try:
                fallback_plans = self.target.search_read(
                    'sale.subscription.plan',
                    [('billing_period_unit', '=', 'month'), ('billing_period_value', '=', 1)],
                    ['id'],
                    limit=1
                )
                if fallback_plans:
                    logger.info(f"    ✓ Using fallback monthly plan (ID: {fallback_plans[0]['id']})")
                    return fallback_plans[0]['id']
            except:
                pass
        
        return None
    
    def _print_statistics(self):
        """Print migration statistics"""
        logger.info("\n" + "=" * 60)
        logger.info("Migration Statistics")
        logger.info("=" * 60)
        logger.info(f"Contracts processed: {self.stats['contracts_processed']}")
        logger.info(f"Contracts migrated: {self.stats['contracts_migrated']}")
        logger.info(f"Contracts failed: {self.stats['contracts_failed']}")
        logger.info(f"Contracts skipped (no partner): {self.stats['contracts_skipped_no_partner']}")
        logger.info(f"Lines migrated: {self.stats['lines_migrated']}")
        logger.info(f"Lines skipped (no product): {self.stats['lines_skipped_no_product']}")
        if self.stats['errors']:
            logger.info(f"\nErrors ({len(self.stats['errors'])}):")
            for error in self.stats['errors'][:10]:  # Show first 10 errors
                logger.error(f"  - {error}")
            if len(self.stats['errors']) > 10:
                logger.info(f"  ... and {len(self.stats['errors']) - 10} more errors")
        
        logger.info("=" * 60)


def main():
    """Main entry point"""
    
    # ========================================================================
    # CONFIGURATION - Update these values
    # ========================================================================
    
    # Source: Odoo 16 with contract module
    SOURCE_CONFIG = {
        'url': 'https://odoo.ictpack.net',
        'db': 'ictpack',
        'username': 'innocent@ictpack.com',
        'password': '1--_Ips2015-',
    }
    
    # Target: Odoo 19 with subscription module
    TARGET_CONFIG = {
        'url': 'http://127.0.0.1:8069',
        'db': 'upgraded',
        'username': 'innocent@ictpack.com',
        'password': '1--_Ips2015-',
    }
    
    # Migration options
    MIGRATION_OPTIONS = {
        'domain': None,  # Filter contracts, e.g., [('partner_id.name', 'ilike', 'customer')]
        'limit': None,   # Limit number of contracts, e.g., 10 for testing
    }
    
    # ========================================================================
    
    try:
        # Create connections
        source = OdooJSONRPC(**SOURCE_CONFIG)
        target = OdooJSONRPC(**TARGET_CONFIG)
        
        # Run migration
        migrator = ContractToSubscriptionMigration(source, target)
        success = migrator.migrate(
            domain=MIGRATION_OPTIONS['domain'],
            limit=MIGRATION_OPTIONS['limit']
        )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("\n\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\nFatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
