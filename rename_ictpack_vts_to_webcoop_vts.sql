-- =====================================================
-- Rename module ictpack_vts -> webcoop_vts
-- =====================================================
-- The module folder was renamed on disk (custom-addons/ictpack_vts
-- -> custom-addons/webcoop_vts) and all internal references updated.
-- Odoo stores the technical module name in the database
-- (ir_module_module, ir_model_data), so this migration must run
-- BEFORE restarting Odoo with the renamed addon, otherwise Odoo
-- treats webcoop_vts as a brand-new module and ictpack_vts as
-- uninstalled/uninstallable.
--
-- IMPORTANT:
--   * Run on EVERY database where ictpack_vts was installed
--     (dev webcop + production).
--   * Take a DB backup first.
--   * Stop the web container before running, start after.
--   * Wrap in a transaction and verify the SELECT counts before
--     committing.
-- =====================================================

BEGIN;

-- ---------------------------------------------------------
-- STEP 0: Diagnose — confirm the old module exists
-- ---------------------------------------------------------
SELECT id, name, state FROM ir_module_module WHERE name IN ('ictpack_vts', 'webcoop_vts');

-- ---------------------------------------------------------
-- STEP 1: Rename the module registration
-- ---------------------------------------------------------
UPDATE ir_module_module
SET name = 'webcoop_vts'
WHERE name = 'ictpack_vts';

-- ---------------------------------------------------------
-- STEP 2: Update external IDs (ir_model_data)
--         (views, reports, security rules, menus, etc.
--          created by the module — xmlids like
--          ictpack_vts.report_job_card become
--          webcoop_vts.report_job_card)
-- ---------------------------------------------------------
UPDATE ir_model_data
SET module = 'webcoop_vts'
WHERE module = 'ictpack_vts';

-- ---------------------------------------------------------
-- STEP 3: Update system parameters keyed by module name
-- ---------------------------------------------------------
UPDATE ir_config_parameter
SET key = replace(key, 'ictpack_vts.', 'webcoop_vts.')
WHERE key LIKE 'ictpack_vts.%';

-- ---------------------------------------------------------
-- STEP 4: Stored HTML fields may embed asset URLs pointing at
--         /ictpack_vts/static/...  (web_editor content, mail
--         templates saved as html)
-- ---------------------------------------------------------
UPDATE ir_asset
SET path = replace(path, '/ictpack_vts/', '/webcoop_vts/')
WHERE path LIKE '/ictpack_vts/%';

-- ---------------------------------------------------------
-- STEP 5: Verify — everything should now show webcoop_vts
-- ---------------------------------------------------------
SELECT name, state FROM ir_module_module WHERE name IN ('ictpack_vts', 'webcoop_vts');
SELECT module, count(*) FROM ir_model_data WHERE module IN ('ictpack_vts', 'webcoop_vts') GROUP BY module;

-- If the above looks correct, commit; otherwise ROLLBACK;
COMMIT;
