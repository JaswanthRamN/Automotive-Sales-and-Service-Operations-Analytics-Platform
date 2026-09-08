BEGIN;

CREATE TABLE IF NOT EXISTS analytics.fact_sales (
    sales_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_id VARCHAR(20) NOT NULL UNIQUE,
    sale_date_key INTEGER NOT NULL,
    customer_key BIGINT NOT NULL,
    vehicle_key BIGINT NOT NULL,
    dealership_key BIGINT NOT NULL,
    salesperson_key BIGINT NOT NULL,
    sales_channel VARCHAR(20) NOT NULL,
    list_price NUMERIC(14, 2) NOT NULL,
    discount_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    sale_price NUMERIC(14, 2) NOT NULL,
    vehicle_cost NUMERIC(14, 2) NOT NULL,
    gross_profit NUMERIC(14, 2) NOT NULL,
    unit_quantity SMALLINT NOT NULL DEFAULT 1,
    payment_type VARCHAR(20) NOT NULL,
    sale_status VARCHAR(20) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_fact_sales_date FOREIGN KEY (sale_date_key)
        REFERENCES analytics.dim_date (date_key),
    CONSTRAINT fk_fact_sales_customer FOREIGN KEY (customer_key)
        REFERENCES analytics.dim_customer (customer_key),
    CONSTRAINT fk_fact_sales_vehicle FOREIGN KEY (vehicle_key)
        REFERENCES analytics.dim_vehicle (vehicle_key),
    CONSTRAINT fk_fact_sales_dealership FOREIGN KEY (dealership_key)
        REFERENCES analytics.dim_dealership (dealership_key),
    CONSTRAINT fk_fact_sales_salesperson FOREIGN KEY (salesperson_key)
        REFERENCES analytics.dim_employee (employee_key),
    CONSTRAINT ck_fact_sales_channel CHECK (sales_channel IN ('Showroom', 'Online', 'Fleet', 'Partner')),
    CONSTRAINT ck_fact_sales_payment CHECK (payment_type IN ('Finance', 'Cash', 'Lease')),
    CONSTRAINT ck_fact_sales_status CHECK (sale_status IN ('Completed', 'Returned', 'Cancelled')),
    CONSTRAINT ck_fact_sales_amounts CHECK (
        list_price >= 0 AND discount_amount >= 0 AND sale_price >= 0
        AND vehicle_cost >= 0 AND ABS((list_price - discount_amount) - sale_price) <= 0.02
        AND ABS((sale_price - vehicle_cost) - gross_profit) <= 0.02
    ),
    CONSTRAINT ck_fact_sales_units CHECK (unit_quantity IN (-1, 1))
);

CREATE TABLE IF NOT EXISTS analytics.fact_inventory (
    inventory_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inventory_id VARCHAR(20) NOT NULL,
    snapshot_date_key INTEGER NOT NULL,
    vehicle_key BIGINT NOT NULL,
    dealership_key BIGINT NOT NULL,
    acquired_date DATE NOT NULL,
    inventory_status VARCHAR(30) NOT NULL,
    carrying_cost NUMERIC(14, 2) NOT NULL,
    days_in_inventory INTEGER NOT NULL,
    slow_moving_flag BOOLEAN NOT NULL,
    on_hand_quantity SMALLINT NOT NULL DEFAULT 1,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_fact_inventory_snapshot UNIQUE (inventory_id, snapshot_date_key),
    CONSTRAINT uq_fact_inventory_vehicle_snapshot UNIQUE (vehicle_key, dealership_key, snapshot_date_key),
    CONSTRAINT fk_fact_inventory_date FOREIGN KEY (snapshot_date_key)
        REFERENCES analytics.dim_date (date_key),
    CONSTRAINT fk_fact_inventory_vehicle FOREIGN KEY (vehicle_key)
        REFERENCES analytics.dim_vehicle (vehicle_key),
    CONSTRAINT fk_fact_inventory_dealership FOREIGN KEY (dealership_key)
        REFERENCES analytics.dim_dealership (dealership_key),
    CONSTRAINT ck_fact_inventory_status CHECK (
        inventory_status IN ('Available', 'Reserved', 'In Transit', 'Demonstrator', 'Sold Not Delivered', 'Unavailable')
    ),
    CONSTRAINT ck_fact_inventory_values CHECK (
        carrying_cost >= 0 AND days_in_inventory >= 0 AND on_hand_quantity = 1
    )
);

CREATE TABLE IF NOT EXISTS analytics.fact_service (
    service_fact_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_order_id VARCHAR(20) NOT NULL UNIQUE,
    appointment_id VARCHAR(20) NOT NULL UNIQUE,
    completed_date_key INTEGER NOT NULL,
    customer_key BIGINT NOT NULL,
    vehicle_key BIGINT NOT NULL,
    dealership_key BIGINT NOT NULL,
    service_advisor_key BIGINT NOT NULL,
    technician_key BIGINT NOT NULL,
    service_key SMALLINT NOT NULL,
    opened_at TIMESTAMP NOT NULL,
    promised_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    payer_type VARCHAR(20) NOT NULL,
    labor_revenue NUMERIC(14, 2) NOT NULL DEFAULT 0,
    parts_revenue NUMERIC(14, 2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    service_revenue NUMERIC(14, 2) NOT NULL,
    repair_order_quantity SMALLINT NOT NULL DEFAULT 1,
    completed_on_time BOOLEAN GENERATED ALWAYS AS (completed_at <= promised_at) STORED,
    turnaround_hours NUMERIC(12, 2) GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (completed_at - opened_at)) / 3600.0
    ) STORED,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_fact_service_date FOREIGN KEY (completed_date_key)
        REFERENCES analytics.dim_date (date_key),
    CONSTRAINT fk_fact_service_customer FOREIGN KEY (customer_key)
        REFERENCES analytics.dim_customer (customer_key),
    CONSTRAINT fk_fact_service_vehicle FOREIGN KEY (vehicle_key)
        REFERENCES analytics.dim_vehicle (vehicle_key),
    CONSTRAINT fk_fact_service_dealership FOREIGN KEY (dealership_key)
        REFERENCES analytics.dim_dealership (dealership_key),
    CONSTRAINT fk_fact_service_advisor FOREIGN KEY (service_advisor_key)
        REFERENCES analytics.dim_employee (employee_key),
    CONSTRAINT fk_fact_service_technician FOREIGN KEY (technician_key)
        REFERENCES analytics.dim_employee (employee_key),
    CONSTRAINT fk_fact_service_type FOREIGN KEY (service_key)
        REFERENCES analytics.dim_service (service_key),
    CONSTRAINT ck_fact_service_timestamp_order CHECK (
        opened_at <= promised_at AND opened_at <= completed_at
    ),
    CONSTRAINT ck_fact_service_status CHECK (order_status IN ('Completed', 'Cancelled', 'Reopened')),
    CONSTRAINT ck_fact_service_payer CHECK (payer_type IN ('Customer Pay', 'Warranty', 'Internal')),
    CONSTRAINT ck_fact_service_amounts CHECK (
        labor_revenue >= 0 AND parts_revenue >= 0 AND discount_amount >= 0
        AND service_revenue >= 0
        AND ABS((labor_revenue + parts_revenue - discount_amount) - service_revenue) <= 0.02
    ),
    CONSTRAINT ck_fact_service_quantity CHECK (repair_order_quantity = 1)
);

COMMIT;
