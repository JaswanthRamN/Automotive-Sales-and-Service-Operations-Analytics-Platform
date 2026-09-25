"""Pydantic response contracts for analytics API resources."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HealthResponse(APIModel):
    status: str
    database: str


class SaleStatus(str, Enum):
    completed = "Completed"
    returned = "Returned"


class PaymentType(str, Enum):
    finance = "Finance"
    cash = "Cash"
    lease = "Lease"


class AgingBucket(str, Enum):
    days_0_30 = "0-30"
    days_31_60 = "31-60"
    days_61_90 = "61-90"
    days_91_120 = "91-120"
    days_120_plus = "120+"


class InventoryStatus(str, Enum):
    available = "Available"
    reserved = "Reserved"
    in_transit = "In Transit"
    demonstrator = "Demonstrator"
    sold_not_delivered = "Sold Not Delivered"
    unavailable = "Unavailable"


class ServiceType(str, Enum):
    maintenance = "Maintenance"
    repair = "Repair"
    inspection = "Inspection"
    recall = "Recall"
    tires = "Tires"


class AppointmentStatus(str, Enum):
    completed = "Completed"
    cancelled = "Cancelled"
    no_show = "No Show"
    scheduled = "Scheduled"


class RelationshipSegment(str, Enum):
    sales_only = "Sales Only"
    service_only = "Service Only"
    sales_and_service = "Sales + Service"
    no_activity = "No Activity"


class LifecycleSegment(str, Enum):
    prospect = "Prospect"
    new_customer = "New Customer"
    repeat_customer = "Repeat Customer"


class ActivitySegment(str, Enum):
    active = "Active"
    inactive = "Inactive"
    never_active = "Never Active"


class SalesSummary(APIModel):
    sales_transactions: int
    units_sold: int
    revenue: Decimal
    gross_profit: Decimal
    gross_margin_percent: Decimal | None = None
    average_selling_price: Decimal | None = None


class ServiceRevenueSummary(APIModel):
    appointments: int
    completed_appointments: int
    repair_orders: int
    service_revenue: Decimal
    completion_rate_percent: Decimal | None = None
    average_repair_order: Decimal | None = None


class SalesRecord(APIModel):
    sale_id: str
    sale_date: date
    brand: str
    model: str
    dealership_id: str
    dealership_name: str
    salesperson_name: str
    payment_type: str
    sale_status: str
    units_sold: int
    revenue: Decimal
    gross_profit: Decimal
    gross_margin_percent: Decimal | None = None
    average_selling_price: Decimal | None = None


class InventoryRecord(APIModel):
    inventory_id: str
    snapshot_date: date
    vehicle_id: str
    brand: str
    model: str
    dealership_id: str
    dealership_name: str
    inventory_status: str
    inventory_units: int
    inventory_value: Decimal
    days_in_inventory: int
    aging_bucket: str
    is_slow_moving: bool


class ServiceRecord(APIModel):
    appointment_id: str
    appointment_date: date
    appointment_time: time
    dealership_id: str
    dealership_name: str
    service_type: str
    appointment_status: str
    service_order_id: str | None = None
    technician_name: str | None = None
    completed_on_time: bool | None = None
    turnaround_hours: Decimal | None = None
    service_revenue: Decimal


class CustomerRecord(APIModel):
    customer_id: str
    customer_name: str
    city: str | None = None
    state: str | None = None
    customer_type: str
    customer_since_date: date
    sales_transaction_count: int
    service_order_count: int
    customer_revenue: Decimal
    customer_lifetime_value: Decimal
    relationship_segment: str
    lifecycle_segment: str
    activity_segment: str
    service_frequency_segment: str


class DealershipRecord(APIModel):
    dealership_id: str
    dealership_name: str
    city: str
    state: str
    region: str
    units_sold: int
    sales_revenue: Decimal
    sales_gross_profit: Decimal
    inventory_units: int
    inventory_value: Decimal
    appointments: int
    service_revenue: Decimal
    unique_customers: int
    total_revenue: Decimal


RecordT = TypeVar("RecordT")


class Page(APIModel, Generic[RecordT]):
    items: list[RecordT]
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)
    returned: int = Field(ge=0)
