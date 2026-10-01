# Power BI semantic model design

This is the model specification for the existing PostgreSQL project, not a
Power BI report implementation. No PBIX, dashboard pages, measures deployment,
database migrations or ETL changes are included.

Read [Star schema](star_schema.md) for tables, grain, keys, relationships and
metric behavior. Read [Power Query](power_query.md) for the import contract and
transformation templates. [Model source validation](model_validation.sql) is a
read-only PostgreSQL acceptance query; every result must be PASS. Also run
`sql/analytics/data_quality.sql` and
`sql/analytics/power_bi_views_validation.sql` before a model refresh.

The dimensional objects live in `analytics`, despite the separate empty
`warehouse` schema. The canonical analytics detail views retain surrogate keys
that the business-friendly `vw_*_performance` views omit. They are therefore
the selected sources for the star, rather than joining flattened business views
by employee names, VINs or dealership names.

Acceptance before future implementation: unique dimension keys, unique fact
grain, zero required-key nulls/orphans, continuous full-year dates, one-way
relationships without cycles, consistent data types, signed sale reversals,
single-snapshot inventory, appointment counts including non-completed outcomes,
and service revenue counted once. Test inactive date roles and employee roles
in the eventual Power BI model; PostgreSQL validation alone cannot establish
Power Query folding, DAX correctness, RLS behavior or Desktop refresh success.

Validation on October 1, 2026: all 16 model-source checks, 28 warehouse quality
checks and 12 reporting-view checks passed against the existing PostgreSQL
database. Repository pytest: 121 passed, one skipped (Airflow is not installed
in the host Python environment). No PostgreSQL objects or ETL code changed.
The Power Query templates and semantic relationship settings are specifications;
their Power BI Desktop execution remains a later implementation acceptance step.

To repeat the model-source gate using a securely configured psql connection:

```sh
psql -v ON_ERROR_STOP=1 -f powerbi/documentation/model_validation.sql
```

SQL syntax errors stop execution; returned FAIL rows must also block acceptance
even if psql itself exits zero. Configure connection details via your usual
PostgreSQL environment/service profile; do not place passwords in the command.

Microsoft references: [star schema guidance](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema),
[active and inactive relationships](https://learn.microsoft.com/en-us/power-bi/guidance/relationships-active-inactive),
[date tables](https://learn.microsoft.com/en-us/power-bi/guidance/model-date-tables),
[PostgreSQL connector](https://learn.microsoft.com/en-us/power-query/connectors/postgresql),
and [native query folding](https://learn.microsoft.com/en-us/power-query/native-query-folding).
