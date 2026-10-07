-- =====================================================
-- Fix corrupted analytic_distribution in account_move_line
-- =====================================================
-- Problem: Some move lines have analytic_distribution keys that are
--          JSON-stringified dicts, e.g. {"{\"1\": 8399}": 100}
--          instead of the correct {"8399": 100}.
--          This causes: ValueError: invalid literal for int() with base 10: '{"1": 8399}'
--          when posting the invoice.
--
-- Run this on the PRODUCTION database (odoo.ictpack.net).
-- =====================================================

-- STEP 1: Diagnose — see which records are corrupted
SELECT id, move_id, analytic_distribution
FROM account_move_line
WHERE analytic_distribution IS NOT NULL
  AND analytic_distribution::text LIKE '%{"%'
  AND analytic_distribution::text LIKE '%"}%'
  AND analytic_distribution::text != '{}';

-- STEP 2: Fix — extract the real account ID from the nested JSON key
-- Converts:  {"{\"1\": 8399}": 100}  -->  {"8399": 100}
UPDATE account_move_line aml
SET analytic_distribution = sub.fixed
FROM (
    SELECT
        aml2.id,
        json_object_agg(
            (SELECT regexp_matches(key, '\d+', 'g') LIMIT 1)[1],
            value
        ) AS fixed
    FROM account_move_line aml2,
         json_each_text(aml2.analytic_distribution) AS je(key, value)
    WHERE aml2.analytic_distribution IS NOT NULL
      AND aml2.analytic_distribution::text LIKE '%{"%'
      AND aml2.analytic_distribution::text LIKE '%"}%'
      AND aml2.analytic_distribution::text != '{}'
    GROUP BY aml2.id
) sub
WHERE aml.id = sub.id;

-- STEP 3: Verify — re-run the diagnostic query, should return 0 rows
SELECT count(*) AS remaining_corrupted
FROM account_move_line
WHERE analytic_distribution IS NOT NULL
  AND analytic_distribution::text LIKE '%{"%'
  AND analytic_distribution::text LIKE '%"}%'
  AND analytic_distribution::text != '{}';
