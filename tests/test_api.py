from __future__ import annotations

import asyncio
from datetime import date, time
from decimal import Decimal
from pathlib import Path
import sys

import httpx
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.database import get_connection  # noqa: E402
from api.main import app  # noqa: E402


class FakeMappings:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, object]]:
        return self.rows

    def one(self) -> dict[str, object]:
        assert len(self.rows) == 1
        return self.rows[0]


class FakeResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []

    def scalar_one(self) -> int:
        return 1

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.statements: list[tuple[str, dict[str, int] | None]] = []
        self.rows = rows or []

    def execute(self, statement: object, parameters: dict[str, int] | None = None) -> FakeResult:
        self.statements.append((str(statement), parameters))
        return FakeResult(self.rows)


class FailingConnection(FakeConnection):
    def execute(self, statement: object, parameters: dict[str, int] | None = None) -> FakeResult:
        raise SQLAlchemyError("private query failure")


async def _async_get(path: str, *, params: dict[str, int] | None = None, raise_app_exceptions: bool = True):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, params=params)


def _get(
    connection: FakeConnection,
    path: str,
    *,
    params: dict[str, int] | None = None,
):
    def override_connection():
        yield connection

    app.dependency_overrides[get_connection] = override_connection
    try:
        return asyncio.run(_async_get(path, params=params))
    finally:
        app.dependency_overrides.clear()


def test_health_checks_database_connection() -> None:
    connection = FakeConnection()
    response = _get(connection, "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}
    assert connection.statements[0][0] == "SELECT 1"


def test_analytics_endpoints_query_only_their_curated_views() -> None:
    expected_views = {
        "/sales": "analytics.vw_sales_performance",
        "/inventory": "analytics.vw_inventory_aging",
        "/service": "analytics.vw_service_performance",
        "/customers": "analytics.vw_customer_value",
        "/dealerships": "analytics.vw_dealership_performance",
    }

    for path, view in expected_views.items():
        connection = FakeConnection()
        response = _get(connection, path, params={"limit": 25, "offset": 10})

        assert response.status_code == 200
        assert response.json() == {"items": [], "limit": 25, "offset": 10, "returned": 0}
        statement, parameters = connection.statements[0]
        assert f"FROM {view}" in statement
        assert parameters == {"limit": 25, "offset": 10}
        assert "SELECT *" not in statement.upper()


def test_pagination_is_validated_before_query_execution() -> None:
    connection = FakeConnection()
    response = _get(connection, "/sales", params={"limit": 501})

    assert response.status_code == 422
    assert connection.statements == []


def test_new_paginated_endpoints_use_curated_views() -> None:
    expected_views = {
        "/sales/performance": "analytics.vw_sales_performance",
        "/inventory/aging": "analytics.vw_inventory_aging",
        "/inventory/slow-moving": "analytics.vw_inventory_aging",
        "/service/performance": "analytics.vw_service_performance",
        "/customers/value": "analytics.vw_customer_value",
        "/dealerships/performance": "analytics.vw_dealership_performance",
    }
    for path, view in expected_views.items():
        connection = FakeConnection()
        response = _get(connection, path, params={"limit": 20, "offset": 5})

        assert response.status_code == 200, response.text
        assert response.json()["returned"] == 0
        statement, parameters = connection.statements[0]
        assert f"FROM {view}" in statement
        assert parameters["limit"] == 20
        assert parameters["offset"] == 5


def test_summary_endpoints_return_validated_aggregates() -> None:
    sales_row = {
        "sales_transactions": 10,
        "units_sold": 8,
        "revenue": 250000,
        "gross_profit": 40000,
        "gross_margin_percent": 16,
        "average_selling_price": 31250,
    }
    service_row = {
        "appointments": 12,
        "completed_appointments": 10,
        "repair_orders": 10,
        "service_revenue": 5400,
        "completion_rate_percent": 83.33,
        "average_repair_order": 540,
    }

    sales_response = _get(FakeConnection([sales_row]), "/sales/summary")
    service_response = _get(FakeConnection([service_row]), "/service/revenue")

    assert sales_response.status_code == 200
    assert sales_response.json()["sales_transactions"] == 10
    assert service_response.status_code == 200
    assert service_response.json()["service_revenue"] == "5400"


def test_successful_resource_responses_match_pydantic_schemas() -> None:
    cases = (
        ("/sales/performance", {
            "sale_id": "SAL001", "sale_date": date(2025, 1, 2), "brand": "Toyota",
            "model": "Camry", "dealership_id": "DLR001", "dealership_name": "Central Auto",
            "salesperson_name": "Alex Smith", "payment_type": "Finance", "sale_status": "Completed",
            "units_sold": 1, "revenue": Decimal("32000.50"), "gross_profit": Decimal("4500.25"),
            "gross_margin_percent": Decimal("14.06"), "average_selling_price": Decimal("32000.50"),
        }, "sale_id"),
        ("/inventory/aging", {
            "inventory_id": "INV001", "snapshot_date": date(2025, 1, 3), "vehicle_id": "VEH001",
            "brand": "Honda", "model": "Civic", "dealership_id": "DLR001",
            "dealership_name": "Central Auto", "inventory_status": "Available", "inventory_units": 1,
            "inventory_value": Decimal("24000"), "days_in_inventory": 45, "aging_bucket": "31-60",
            "is_slow_moving": False,
        }, "inventory_id"),
        ("/service/performance", {
            "appointment_id": "APT001", "appointment_date": date(2025, 1, 4),
            "appointment_time": time(9, 30), "dealership_id": "DLR001", "dealership_name": "Central Auto",
            "service_type": "Maintenance", "appointment_status": "Completed", "service_order_id": "SVC001",
            "technician_name": "Pat Lee", "completed_on_time": True,
            "turnaround_hours": Decimal("2.50"), "service_revenue": Decimal("425.75"),
        }, "appointment_id"),
        ("/customers/value", {
            "customer_id": "CUS001", "customer_name": "Jordan Taylor", "city": "Austin", "state": "Texas",
            "customer_type": "Individual", "customer_since_date": date(2023, 2, 1),
            "sales_transaction_count": 2, "service_order_count": 4, "customer_revenue": Decimal("71000"),
            "customer_lifetime_value": Decimal("71000"), "relationship_segment": "Sales + Service",
            "lifecycle_segment": "Repeat Customer", "activity_segment": "Active",
            "service_frequency_segment": "Frequent Service",
        }, "customer_id"),
        ("/dealerships/performance", {
            "dealership_id": "DLR001", "dealership_name": "Central Auto", "city": "Austin",
            "state": "Texas", "region": "South", "units_sold": 100,
            "sales_revenue": Decimal("3200000"), "sales_gross_profit": Decimal("450000"),
            "inventory_units": 50, "inventory_value": Decimal("1400000"), "appointments": 180,
            "service_revenue": Decimal("90000"), "unique_customers": 220,
            "total_revenue": Decimal("3290000"),
        }, "dealership_id"),
    )

    for path, row, identity_field in cases:
        response = _get(FakeConnection([row]), path)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["returned"] == 1
        assert payload["items"][0][identity_field] == row[identity_field]
        assert set(payload) == {"items", "limit", "offset", "returned"}


def test_filters_are_parameterized_and_slow_moving_is_mandatory() -> None:
    connection = FakeConnection()
    response = _get(
        connection,
        "/sales/performance",
        params={
            "date_from": "2025-01-01",
            "date_to": "2025-06-30",
            "dealership_id": "DLR001",
            "brand": "Toyota",
            "payment_type": "Finance",
            "sale_status": "Completed",
        },
    )
    assert response.status_code == 200
    statement, parameters = connection.statements[0]
    assert "sale_date >= :date_from" in statement
    assert "dealership_id = :dealership_id" in statement
    assert "brand = :brand" in statement
    assert "Toyota" not in statement
    assert parameters["brand"] == "Toyota"
    assert parameters["payment_type"] == "Finance"

    slow_connection = FakeConnection()
    slow_response = _get(slow_connection, "/inventory/slow-moving")
    assert slow_response.status_code == 200
    slow_statement, slow_parameters = slow_connection.statements[0]
    assert "is_slow_moving = :slow_only" in slow_statement
    assert slow_parameters["slow_only"] is True


def test_invalid_ranges_categories_and_numeric_filters_never_query_database() -> None:
    cases = (
        ("/sales/performance", {"date_from": "2025-05-02", "date_to": "2025-05-01"}),
        ("/inventory/aging", {"aging_bucket": "invalid"}),
        ("/inventory/aging", {"inventory_status": "Lost"}),
        ("/service/performance", {"appointment_status": "Unknown"}),
        ("/service/performance", {"service_type": "Detailing"}),
        ("/customers/value", {"relationship_segment": "Unknown"}),
        ("/customers/value", {"state": "X"}),
        ("/customers/value", {"minimum_value": -1}),
        ("/dealerships/performance", {"minimum_revenue": -1}),
        ("/sales/performance", {"date_from": "not-a-date"}),
        ("/sales/performance", {"offset": -1}),
        ("/sales/performance", {"limit": 0}),
    )
    for path, params in cases:
        connection = FakeConnection()
        response = _get(connection, path, params=params)
        assert response.status_code == 422
        assert connection.statements == []


def test_database_errors_return_sanitized_service_unavailable() -> None:
    def failing_connection():
        raise SQLAlchemyError("secret database details")
        yield  # pragma: no cover

    app.dependency_overrides[get_connection] = failing_connection
    try:
        response = asyncio.run(_async_get("/health", raise_app_exceptions=False))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "The analytics database is temporarily unavailable."}
    assert "secret database details" not in response.text

    analytics_response = _get(FailingConnection(), "/sales", params={"limit": 10})
    assert analytics_response.status_code == 503
    assert analytics_response.json()["detail"] == "The analytics database is temporarily unavailable."
    assert "private query failure" not in analytics_response.text


def test_openapi_documents_all_routes_and_response_models() -> None:
    schema = asyncio.run(_async_get("/openapi.json")).json()
    docs = asyncio.run(_async_get("/docs"))

    assert docs.status_code == 200
    for path in (
        "/health", "/sales", "/inventory", "/service", "/customers", "/dealerships",
        "/sales/summary", "/sales/performance", "/inventory/aging",
        "/inventory/slow-moving", "/service/revenue", "/service/performance",
        "/customers/value", "/dealerships/performance",
    ):
        assert path in schema["paths"]
        assert "get" in schema["paths"][path]
        assert "200" in schema["paths"][path]["get"]["responses"]
    assert schema["info"]["title"] == "Automotive Sales & Service Analytics API"
    assert "SalesRecord" in schema["components"]["schemas"]
