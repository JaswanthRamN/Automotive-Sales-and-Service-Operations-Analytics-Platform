"""Read-only FastAPI service for PostgreSQL automotive analytics views."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os
import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError

from api.database import dispose_engine, get_connection
from api.models import (
    CustomerRecord,
    DealershipRecord,
    HealthResponse,
    InventoryRecord,
    Page,
    SalesRecord,
    ServiceRecord,
)


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)

ConnectionDependency = Annotated[Connection, Depends(get_connection)]
Limit = Annotated[int, Query(ge=1, le=500, description="Maximum records to return")]
Offset = Annotated[int, Query(ge=0, description="Records to skip")]


@asynccontextmanager
async def lifespan(_: FastAPI):
    LOGGER.info("Automotive analytics API starting")
    yield
    dispose_engine()
    LOGGER.info("Automotive analytics API stopped")


app = FastAPI(
    title="Automotive Sales & Service Analytics API",
    summary="Read-only access to curated PostgreSQL analytics views",
    description=(
        "Business-friendly sales, inventory, service, customer-value, and dealership "
        "analytics. Interactive Swagger documentation is available at `/docs`."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Operations", "description": "Service readiness"},
        {"name": "Analytics", "description": "Paginated, read-only analytics resources"},
    ],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception("Unhandled request failure: method=%s path=%s", request.method, request.url.path)
        raise
    LOGGER.info(
        "Request completed: method=%s path=%s status=%d duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    LOGGER.error("Database request failed: path=%s error=%s", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "The analytics database is temporarily unavailable."},
    )


def _fetch_page(
    connection: Connection,
    *,
    select_columns: str,
    view: str,
    order_by: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    statement = text(
        f"SELECT {select_columns} FROM analytics.{view} "
        f"ORDER BY {order_by} LIMIT :limit OFFSET :offset"
    )
    rows = connection.execute(statement, {"limit": limit, "offset": offset}).mappings().all()
    items = [dict(row) for row in rows]
    return {"items": items, "limit": limit, "offset": offset, "returned": len(items)}


@app.get("/health", response_model=HealthResponse, tags=["Operations"])
def health(connection: ConnectionDependency) -> HealthResponse:
    connection.execute(text("SELECT 1")).scalar_one()
    return HealthResponse(status="healthy", database="connected")


@app.get("/sales", response_model=Page[SalesRecord], tags=["Analytics"])
def sales(connection: ConnectionDependency, limit: Limit = 100, offset: Offset = 0):
    return _fetch_page(
        connection,
        select_columns=(
            "sale_id, sale_date, brand, model, dealership_id, dealership_name, "
            "salesperson_name, payment_type, sale_status, units_sold, revenue, "
            "gross_profit, gross_margin_percent, average_selling_price"
        ),
        view="vw_sales_performance",
        order_by="sale_date DESC, sale_id",
        limit=limit,
        offset=offset,
    )


@app.get("/inventory", response_model=Page[InventoryRecord], tags=["Analytics"])
def inventory(connection: ConnectionDependency, limit: Limit = 100, offset: Offset = 0):
    return _fetch_page(
        connection,
        select_columns=(
            "inventory_id, snapshot_date, vehicle_id, brand, model, dealership_id, "
            "dealership_name, inventory_status, inventory_units, inventory_value, "
            "days_in_inventory, aging_bucket, is_slow_moving"
        ),
        view="vw_inventory_aging",
        order_by="snapshot_date DESC, inventory_id",
        limit=limit,
        offset=offset,
    )


@app.get("/service", response_model=Page[ServiceRecord], tags=["Analytics"])
def service(connection: ConnectionDependency, limit: Limit = 100, offset: Offset = 0):
    return _fetch_page(
        connection,
        select_columns=(
            "appointment_id, appointment_date, appointment_time, dealership_id, "
            "dealership_name, service_type, appointment_status, service_order_id, "
            "technician_name, completed_on_time, turnaround_hours, service_revenue"
        ),
        view="vw_service_performance",
        order_by="appointment_date DESC, appointment_id",
        limit=limit,
        offset=offset,
    )


@app.get("/customers", response_model=Page[CustomerRecord], tags=["Analytics"])
def customers(connection: ConnectionDependency, limit: Limit = 100, offset: Offset = 0):
    return _fetch_page(
        connection,
        select_columns=(
            "customer_id, customer_name, city, state, customer_type, customer_since_date, "
            "sales_transaction_count, service_order_count, customer_revenue, "
            "customer_lifetime_value, relationship_segment, lifecycle_segment, "
            "activity_segment, service_frequency_segment"
        ),
        view="vw_customer_value",
        order_by="customer_lifetime_value DESC, customer_id",
        limit=limit,
        offset=offset,
    )


@app.get("/dealerships", response_model=Page[DealershipRecord], tags=["Analytics"])
def dealerships(connection: ConnectionDependency, limit: Limit = 100, offset: Offset = 0):
    return _fetch_page(
        connection,
        select_columns=(
            "dealership_id, dealership_name, city, state, region, units_sold, sales_revenue, "
            "sales_gross_profit, inventory_units, inventory_value, appointments, "
            "service_revenue, unique_customers, total_revenue"
        ),
        view="vw_dealership_performance",
        order_by="total_revenue DESC, dealership_id",
        limit=limit,
        offset=offset,
    )
