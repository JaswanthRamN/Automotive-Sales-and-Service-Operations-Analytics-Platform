"""Verify populated PostgreSQL, SQL quality gates and the live FastAPI API.

Run after a successful Airflow DAG: python scripts/verify_runtime.py.
This check is read-only and exits nonzero on any mismatch.
"""
from pathlib import Path
import json
import os
import sys
from decimal import Decimal
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sqlalchemy import create_engine, text
from automotive_analytics.etl import (
    DATASETS, ETLConfig, WAREHOUSE_SOURCE_COUNTS, query_counts,
    validate_database_counts, validate_processed_files,
)


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    config = ETLConfig.from_env(env_file=ROOT / ".env")
    base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")

    def request(path, expected=200):
        try:
            with urlopen(base + path, timeout=30) as response:
                status, body = response.status, json.load(response)
        except HTTPError as error:
            status, body = error.code, json.load(error)
        check(status == expected, f"{path}: expected {expected}, got {status}: {body}")
        return body

    source = validate_processed_files(ROOT / "data/processed")
    print(f"Source preflight: PASS ({sum(source.values())} rows)", flush=True)
    engine = create_engine(config.database_url, connect_args={"connect_timeout": 10})
    try:
        with engine.connect() as connection:
            print("PostgreSQL connected", flush=True)
            staging = query_counts(connection, [f"staging.{name}" for name in DATASETS])
            warehouse = query_counts(connection, list(WAREHOUSE_SOURCE_COUNTS) + [
                "analytics.dim_date", "analytics.dim_service"])
            validate_database_counts(source, staging, warehouse)
            quality = connection.exec_driver_sql(
                (ROOT / "sql/analytics/data_quality.sql").read_text(encoding="utf-8")
            ).mappings().all()
            check(bool(quality), "No quality checks returned")
            check(all(row["status"] == "PASS" for row in quality), str(quality))
            print(f"Row counts and {len(quality)} SQL quality checks: PASS", flush=True)
            sales_totals = connection.execute(text(
                "SELECT count(*), sum(units_sold), sum(revenue), sum(gross_profit) "
                "FROM analytics.vw_sales_performance"
            )).one()
            service_totals = connection.execute(text(
                "SELECT count(*), count(service_order_id), sum(service_revenue) "
                "FROM analytics.vw_service_performance"
            )).one()
        check(request("/health")["database"] == "connected", "API database unhealthy")
        routes = ("/sales", "/inventory", "/service", "/customers", "/dealerships",
                  "/sales/performance", "/inventory/aging", "/inventory/slow-moving",
                  "/service/performance", "/customers/value", "/dealerships/performance")
        for route in routes:
            page = request(route + "?limit=2")
            check(page["returned"] == len(page["items"]) > 0, f"Empty/invalid page: {route}")
            check(page["limit"] == 2 and page["returned"] <= 2, f"Pagination: {route}")
            print(f"API {route}: PASS", flush=True)
        first, second = request("/sales?limit=2"), request("/sales?limit=2&offset=2")
        check(not ({r["sale_id"] for r in first["items"]} &
                   {r["sale_id"] for r in second["items"]}), "Overlapping pages")
        filtered = request("/sales/performance?brand=" + first["items"][0]["brand"])
        check(all(r["brand"] == first["items"][0]["brand"] for r in filtered["items"]),
              "Brand filter mismatch")
        check(request("/sales/performance?brand=DOES_NOT_EXIST")["returned"] == 0,
              "Expected empty filtered page")
        for path in ("/sales?limit=0", "/sales?offset=-1", "/sales/performance?payment_type=bad",
                     "/sales/summary?date_from=2025-01-01&date_to=2024-01-01"):
            request(path, expected=422)
        sales = request("/sales/summary")
        for field, expected in zip(("sales_transactions", "units_sold", "revenue", "gross_profit"), sales_totals):
            check(Decimal(str(sales[field])) == expected, f"Sales total mismatch: {field}")
        service = request("/service/revenue")
        for field, expected in zip(("appointments", "repair_orders", "service_revenue"), service_totals):
            check(Decimal(str(service[field])) == expected, f"Service total mismatch: {field}")
        check("/health" in request("/openapi.json")["paths"], "OpenAPI missing health route")
        print(json.dumps({"status": "PASS", "source_rows": sum(source.values()),
                          "warehouse_counts": warehouse, "quality_checks": len(quality),
                          "api_page_routes": len(routes)}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
