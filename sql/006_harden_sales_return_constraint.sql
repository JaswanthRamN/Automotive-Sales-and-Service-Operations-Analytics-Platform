BEGIN;

-- Upgrade databases created before sale status and unit sign were coupled.
ALTER TABLE analytics.fact_sales
    DROP CONSTRAINT IF EXISTS ck_fact_sales_units;

UPDATE analytics.fact_sales
SET unit_quantity = CASE
    WHEN sale_status = 'Returned' THEN -1
    ELSE 1
END
WHERE unit_quantity IS DISTINCT FROM CASE
    WHEN sale_status = 'Returned' THEN -1
    ELSE 1
END;

ALTER TABLE analytics.fact_sales
    ADD CONSTRAINT ck_fact_sales_units CHECK (
        (sale_status = 'Returned' AND unit_quantity = -1)
        OR (sale_status IN ('Completed', 'Cancelled') AND unit_quantity = 1)
    );

COMMIT;
