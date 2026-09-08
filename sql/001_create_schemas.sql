BEGIN;

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA staging IS 'Landing tables for cleaned source files before dimensional transformation.';
COMMENT ON SCHEMA analytics IS 'Conformed dimensions and sales, inventory, and service facts.';

COMMIT;
