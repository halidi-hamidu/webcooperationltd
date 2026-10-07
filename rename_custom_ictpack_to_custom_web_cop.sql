-- =====================================================
-- Rename module custom_ictpack -> custom_web_cop
-- =====================================================
-- The module folder was renamed on disk. Odoo stores the technical
-- module name in the database (ir_module_module, ir_model_data, and
-- config parameters keyed by "custom_ictpack.*"), so the database
-- must be migrated BEFORE restarting Odoo with the renamed addon,
-- otherwise Odoo will treat custom_web_cop as a brand-new module
-- and custom_ictpack as uninstalled/uninstallable.
--
-- IMPORTANT:
--   * Run this on EVERY database where custom_ictpack was installed
--     (dev + prod).
--   * Take a DB backup first.
--   * Wrap in a transaction (BEGIN; ... COMMIT;) and verify the SELECT
--     counts before committing.
-- =====================================================

BEGIN;

-- ---------------------------------------------------------
-- STEP 0: Diagnose — confirm the old module exists
-- ---------------------------------------------------------
SELECT id, name, state FROM ir_module_module WHERE name IN ('custom_ictpack', 'custom_web_cop');

-- ---------------------------------------------------------
-- STEP 1: Rename the module registration
-- ---------------------------------------------------------
UPDATE ir_module_module
SET name = 'custom_web_cop',
    latest_version = '1.0.0'
WHERE name = 'custom_ictpack';

-- ---------------------------------------------------------
-- STEP 2: Update external IDs (ir_model_data)
--         (records created by the module: views, reports,
--          security rules, sequences, actions, etc.)
-- ---------------------------------------------------------
UPDATE ir_model_data
SET module = 'custom_web_cop'
WHERE module = 'custom_ictpack';

-- ---------------------------------------------------------
-- STEP 3: Update system parameters
--         (res.config.settings fields use config_parameter
--          keys prefixed with the module name)
-- ---------------------------------------------------------
UPDATE ir_config_parameter
SET key = replace(key, 'custom_ictpack.', 'custom_web_cop.')
WHERE key LIKE 'custom_ictpack.%';

-- ---------------------------------------------------------
-- STEP 4: Update company-specific assets (report layouts that
--         reference /custom_ictpack/static/... URLs are in XML
--         files and are reloaded on upgrade, but any stored
--         web_editor / html fields may embed the URL)
-- ---------------------------------------------------------
UPDATE ir_asset
SET path = replace(path, '/custom_ictpack/', '/custom_web_cop/')
WHERE path LIKE '/custom_ictpack/%';

-- ---------------------------------------------------------
-- STEP 5: Verify — everything should now show custom_web_cop
-- ---------------------------------------------------------
SELECT name, state FROM ir_module_module WHERE name IN ('custom_ictpack', 'custom_web_cop');
SELECT module, count(*) FROM ir_model_data WHERE module IN ('custom_ictpack', 'custom_web_cop') GROUP BY module;
SELECT key FROM ir_config_parameter WHERE key LIKE 'custom_web_cop.%';

-- If the above looks correct, commit; otherwise ROLLBACK;
COMMIT;
