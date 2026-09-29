"""Create empty warehouse tables and reporting views without loading data."""
from pathlib import Path
from sqlalchemy import create_engine
from automotive_analytics.etl import ETLConfig, apply_schema


def bootstrap():
    root = Path(__file__).resolve().parents[1]
    engine = create_engine(ETLConfig.from_env(env_file=None).database_url)
    try:
        with engine.begin() as connection:
            apply_schema(connection, root / "sql")
            # Send complete scripts: view comments can contain semicolons.
            for name in ("sales_analytics", "inventory_analytics", "service_analytics",
                         "customer_analytics", "power_bi_views"):
                sql = (root / "sql" / "analytics" / f"{name}.sql").read_text()
                sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
                connection.exec_driver_sql(sql)
    finally:
        engine.dispose()


if __name__ == "__main__":
    bootstrap()
