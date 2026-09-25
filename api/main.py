"""Read-only FastAPI service for PostgreSQL automotive analytics views."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
import logging
import os
import time
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError

from api.database import dispose_engine, get_connection
from api.models import (
    CustomerRecord,
    DealershipRecord,
    ActivitySegment,
    AgingBucket,
    AppointmentStatus,
    HealthResponse,
    InventoryRecord,
    InventoryStatus,
    Page,
    PaymentType,
    RelationshipSegment,
    LifecycleSegment,
    SaleStatus,
    SalesRecord,
    SalesSummary,
    ServiceRecord,
    ServiceRevenueSummary,
    ServiceType,
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
ShortCode = Annotated[str | None, Query(min_length=1, max_length=60)]


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
    filters: list[tuple[str, str, Any]] | None = None,
) -> dict[str, Any]:
    where_sql, parameters = _build_where(filters or [])
    statement = text(
        f"SELECT {select_columns} FROM analytics.{view} "
        f"{where_sql} "
        f"ORDER BY {order_by} LIMIT :limit OFFSET :offset"
    )
    parameters.update({"limit": limit, "offset": offset})
    rows = connection.execute(statement, parameters).mappings().all()
    items = [dict(row) for row in rows]
    return {"items": items, "limit": limit, "offset": offset, "returned": len(items)}


def _build_where(filters: list[tuple[str, str, Any]]) -> tuple[str, dict[str, Any]]:
    active = [(clause, name, value) for clause, name, value in filters if value is not None]
    if not active:
        return "", {}
    return "WHERE " + " AND ".join(item[0] for item in active), {
        name: value.value if hasattr(value, "value") else value for _, name, value in active
    }


def _validate_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")


def _fetch_summary(
    connection: Connection,
    *,
    select_columns: str,
    view: str,
    filters: list[tuple[str, str, Any]],
) -> dict[str, Any]:
    where_sql, parameters = _build_where(filters)
    statement = text(f"SELECT {select_columns} FROM analytics.{view} {where_sql}")
    return dict(connection.execute(statement, parameters).mappings().one())


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


def _sales_filters(
    date_from: date | None,
    date_to: date | None,
    dealership_id: str | None,
    brand: str | None,
    payment_type: PaymentType | None,
    sale_status: SaleStatus | None,
) -> list[tuple[str, str, Any]]:
    _validate_date_range(date_from, date_to)
    return [
        ("sale_date >= :date_from", "date_from", date_from),
        ("sale_date <= :date_to", "date_to", date_to),
        ("dealership_id = :dealership_id", "dealership_id", dealership_id),
        ("brand = :brand", "brand", brand),
        ("payment_type = :payment_type", "payment_type", payment_type),
        ("sale_status = :sale_status", "sale_status", sale_status),
    ]


@app.get("/sales/summary", response_model=SalesSummary, tags=["Analytics"])
def sales_summary(
    connection: ConnectionDependency,
    date_from: date | None = None,
    date_to: date | None = None,
    dealership_id: ShortCode = None,
    brand: ShortCode = None,
    payment_type: PaymentType | None = None,
    sale_status: SaleStatus | None = None,
):
    return _fetch_summary(
        connection,
        select_columns=(
            "COUNT(*)::BIGINT AS sales_transactions, "
            "COALESCE(SUM(units_sold), 0)::BIGINT AS units_sold, "
            "COALESCE(SUM(revenue), 0)::NUMERIC AS revenue, "
            "COALESCE(SUM(gross_profit), 0)::NUMERIC AS gross_profit, "
            "ROUND(SUM(gross_profit) / NULLIF(SUM(revenue), 0) * 100, 2) AS gross_margin_percent, "
            "ROUND(SUM(revenue) / NULLIF(SUM(units_sold), 0), 2) AS average_selling_price"
        ),
        view="vw_sales_performance",
        filters=_sales_filters(date_from, date_to, dealership_id, brand, payment_type, sale_status),
    )


@app.get("/sales/performance", response_model=Page[SalesRecord], tags=["Analytics"])
def sales_performance(
    connection: ConnectionDependency,
    limit: Limit = 100,
    offset: Offset = 0,
    date_from: date | None = None,
    date_to: date | None = None,
    dealership_id: ShortCode = None,
    brand: ShortCode = None,
    payment_type: PaymentType | None = None,
    sale_status: SaleStatus | None = None,
):
    return _fetch_page(
        connection,
        select_columns=(
            "sale_id, sale_date, brand, model, dealership_id, dealership_name, "
            "salesperson_name, payment_type, sale_status, units_sold, revenue, gross_profit, "
            "gross_margin_percent, average_selling_price"
        ),
        view="vw_sales_performance",
        order_by="sale_date DESC, sale_id",
        limit=limit,
        offset=offset,
        filters=_sales_filters(date_from, date_to, dealership_id, brand, payment_type, sale_status),
    )


def _inventory_filters(
    date_from: date | None,
    date_to: date | None,
    dealership_id: str | None,
    brand: str | None,
    aging_bucket: AgingBucket | None,
    inventory_status: InventoryStatus | None,
    slow_only: bool | None = None,
) -> list[tuple[str, str, Any]]:
    _validate_date_range(date_from, date_to)
    return [
        ("snapshot_date >= :date_from", "date_from", date_from),
        ("snapshot_date <= :date_to", "date_to", date_to),
        ("dealership_id = :dealership_id", "dealership_id", dealership_id),
        ("brand = :brand", "brand", brand),
        ("aging_bucket = :aging_bucket", "aging_bucket", aging_bucket),
        ("inventory_status = :inventory_status", "inventory_status", inventory_status),
        ("is_slow_moving = :slow_only", "slow_only", slow_only),
    ]


@app.get("/inventory/aging", response_model=Page[InventoryRecord], tags=["Analytics"])
def inventory_aging(
    connection: ConnectionDependency,
    limit: Limit = 100,
    offset: Offset = 0,
    date_from: date | None = None,
    date_to: date | None = None,
    dealership_id: ShortCode = None,
    brand: ShortCode = None,
    aging_bucket: AgingBucket | None = None,
    inventory_status: InventoryStatus | None = None,
):
    return _fetch_page(
        connection,
        select_columns=(
            "inventory_id, snapshot_date, vehicle_id, brand, model, dealership_id, dealership_name, "
            "inventory_status, inventory_units, inventory_value, days_in_inventory, aging_bucket, is_slow_moving"
        ),
        view="vw_inventory_aging",
        order_by="snapshot_date DESC, days_in_inventory DESC, inventory_id",
        limit=limit,
        offset=offset,
        filters=_inventory_filters(date_from, date_to, dealership_id, brand, aging_bucket, inventory_status),
    )


@app.get("/inventory/slow-moving", response_model=Page[InventoryRecord], tags=["Analytics"])
def inventory_slow_moving(
    connection: ConnectionDependency,
    limit: Limit = 100,
    offset: Offset = 0,
    date_from: date | None = None,
    date_to: date | None = None,
    dealership_id: ShortCode = None,
    brand: ShortCode = None,
    aging_bucket: AgingBucket | None = None,
    inventory_status: InventoryStatus | None = None,
):
    return _fetch_page(
        connection,
        select_columns=(
            "inventory_id, snapshot_date, vehicle_id, brand, model, dealership_id, dealership_name, "
            "inventory_status, inventory_units, inventory_value, days_in_inventory, aging_bucket, is_slow_moving"
        ),
        view="vw_inventory_aging",
        order_by="days_in_inventory DESC, inventory_id",
        limit=limit,
        offset=offset,
        filters=_inventory_filters(
            date_from, date_to, dealership_id, brand, aging_bucket, inventory_status, True
        ),
    )


def _service_filters(
    date_from: date | None,
    date_to: date | None,
    dealership_id: str | None,
    service_type: ServiceType | None,
    appointment_status: AppointmentStatus | None,
) -> list[tuple[str, str, Any]]:
    _validate_date_range(date_from, date_to)
    return [
        ("appointment_date >= :date_from", "date_from", date_from),
        ("appointment_date <= :date_to", "date_to", date_to),
        ("dealership_id = :dealership_id", "dealership_id", dealership_id),
        ("service_type = :service_type", "service_type", service_type),
        ("appointment_status = :appointment_status", "appointment_status", appointment_status),
    ]


@app.get("/service/revenue", response_model=ServiceRevenueSummary, tags=["Analytics"])
def service_revenue(
    connection: ConnectionDependency,
    date_from: date | None = None,
    date_to: date | None = None,
    dealership_id: ShortCode = None,
    service_type: ServiceType | None = None,
    appointment_status: AppointmentStatus | None = None,
):
    return _fetch_summary(
        connection,
        select_columns=(
            "COALESCE(SUM(appointment_count), 0)::BIGINT AS appointments, "
            "COALESCE(SUM(completed_appointment_count), 0)::BIGINT AS completed_appointments, "
            "COUNT(service_order_id)::BIGINT AS repair_orders, "
            "COALESCE(SUM(service_revenue), 0)::NUMERIC AS service_revenue, "
            "ROUND(SUM(completed_appointment_count)::NUMERIC / "
            "NULLIF(SUM(completion_eligible_count), 0) * 100, 2) AS completion_rate_percent, "
            "ROUND(SUM(service_revenue) / NULLIF(COUNT(service_order_id), 0), 2) AS average_repair_order"
        ),
        view="vw_service_performance",
        filters=_service_filters(date_from, date_to, dealership_id, service_type, appointment_status),
    )


@app.get("/service/performance", response_model=Page[ServiceRecord], tags=["Analytics"])
def service_performance(
    connection: ConnectionDependency,
    limit: Limit = 100,
    offset: Offset = 0,
    date_from: date | None = None,
    date_to: date | None = None,
    dealership_id: ShortCode = None,
    service_type: ServiceType | None = None,
    appointment_status: AppointmentStatus | None = None,
):
    return _fetch_page(
        connection,
        select_columns=(
            "appointment_id, appointment_date, appointment_time, dealership_id, dealership_name, "
            "service_type, appointment_status, service_order_id, technician_name, completed_on_time, "
            "turnaround_hours, service_revenue"
        ),
        view="vw_service_performance",
        order_by="appointment_date DESC, appointment_id",
        limit=limit,
        offset=offset,
        filters=_service_filters(date_from, date_to, dealership_id, service_type, appointment_status),
    )


@app.get("/customers/value", response_model=Page[CustomerRecord], tags=["Analytics"])
def customer_value(
    connection: ConnectionDependency,
    limit: Limit = 100,
    offset: Offset = 0,
    state: Annotated[str | None, Query(min_length=2, max_length=50)] = None,
    relationship_segment: RelationshipSegment | None = None,
    lifecycle_segment: LifecycleSegment | None = None,
    activity_segment: ActivitySegment | None = None,
    minimum_value: Annotated[Decimal | None, Query(ge=0)] = None,
):
    return _fetch_page(
        connection,
        select_columns=(
            "customer_id, customer_name, city, state, customer_type, customer_since_date, "
            "sales_transaction_count, service_order_count, customer_revenue, customer_lifetime_value, "
            "relationship_segment, lifecycle_segment, activity_segment, service_frequency_segment"
        ),
        view="vw_customer_value",
        order_by="customer_lifetime_value DESC, customer_id",
        limit=limit,
        offset=offset,
        filters=[
            ("state = :state", "state", state),
            ("relationship_segment = :relationship_segment", "relationship_segment", relationship_segment),
            ("lifecycle_segment = :lifecycle_segment", "lifecycle_segment", lifecycle_segment),
            ("activity_segment = :activity_segment", "activity_segment", activity_segment),
            ("customer_lifetime_value >= :minimum_value", "minimum_value", minimum_value),
        ],
    )


@app.get("/dealerships/performance", response_model=Page[DealershipRecord], tags=["Analytics"])
def dealership_performance(
    connection: ConnectionDependency,
    limit: Limit = 100,
    offset: Offset = 0,
    region: ShortCode = None,
    state: Annotated[str | None, Query(min_length=2, max_length=50)] = None,
    minimum_revenue: Annotated[Decimal | None, Query(ge=0)] = None,
):
    return _fetch_page(
        connection,
        select_columns=(
            "dealership_id, dealership_name, city, state, region, units_sold, sales_revenue, "
            "sales_gross_profit, inventory_units, inventory_value, appointments, service_revenue, "
            "unique_customers, total_revenue"
        ),
        view="vw_dealership_performance",
        order_by="total_revenue DESC, dealership_id",
        limit=limit,
        offset=offset,
        filters=[
            ("region = :region", "region", region),
            ("state = :state", "state", state),
            ("total_revenue >= :minimum_revenue", "minimum_revenue", minimum_revenue),
        ],
    )
