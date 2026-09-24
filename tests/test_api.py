from __future__ import annotations

import asyncio
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


class FakeResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []

    def scalar_one(self) -> int:
        return 1

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, int] | None]] = []

    def execute(self, statement: object, parameters: dict[str, int] | None = None) -> FakeResult:
        self.statements.append((str(statement), parameters))
        return FakeResult()


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


def test_openapi_documents_all_routes_and_response_models() -> None:
    schema = asyncio.run(_async_get("/openapi.json")).json()
    docs = asyncio.run(_async_get("/docs"))

    assert docs.status_code == 200
    for path in ("/health", "/sales", "/inventory", "/service", "/customers", "/dealerships"):
        assert path in schema["paths"]
        assert "get" in schema["paths"][path]
        assert "200" in schema["paths"][path]["get"]["responses"]
    assert schema["info"]["title"] == "Automotive Sales & Service Analytics API"
    assert "SalesRecord" in schema["components"]["schemas"]
