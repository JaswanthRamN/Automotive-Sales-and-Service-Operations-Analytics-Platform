BEGIN;

CREATE TABLE IF NOT EXISTS analytics.dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    day_name VARCHAR(9) NOT NULL,
    day_of_month SMALLINT NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    day_of_year SMALLINT NOT NULL CHECK (day_of_year BETWEEN 1 AND 366),
    week_of_year SMALLINT NOT NULL CHECK (week_of_year BETWEEN 1 AND 53),
    month_number SMALLINT NOT NULL CHECK (month_number BETWEEN 1 AND 12),
    month_name VARCHAR(9) NOT NULL,
    quarter_number SMALLINT NOT NULL CHECK (quarter_number BETWEEN 1 AND 4),
    calendar_year SMALLINT NOT NULL CHECK (calendar_year BETWEEN 2000 AND 2200),
    is_weekend BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics.dim_dealership (
    dealership_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dealership_id VARCHAR(20) NOT NULL UNIQUE,
    dealership_name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(50) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    region VARCHAR(50) NOT NULL,
    opened_date DATE NOT NULL,
    effective_from DATE NOT NULL DEFAULT DATE '1900-01-01',
    effective_to DATE NOT NULL DEFAULT DATE '9999-12-31',
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_dim_dealership_effective_dates CHECK (effective_from <= effective_to)
);

CREATE TABLE IF NOT EXISTS analytics.dim_customer (
    customer_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id VARCHAR(20) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(320),
    phone VARCHAR(30),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    customer_since_date DATE NOT NULL,
    customer_type VARCHAR(20) NOT NULL,
    effective_from DATE NOT NULL DEFAULT DATE '1900-01-01',
    effective_to DATE NOT NULL DEFAULT DATE '9999-12-31',
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_dim_customer_version UNIQUE (customer_id, effective_from),
    CONSTRAINT ck_dim_customer_type CHECK (customer_type IN ('Individual', 'Business', 'Fleet')),
    CONSTRAINT ck_dim_customer_effective_dates CHECK (effective_from <= effective_to)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_customer_current
    ON analytics.dim_customer (customer_id)
    WHERE is_current;

CREATE TABLE IF NOT EXISTS analytics.dim_vehicle (
    vehicle_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vehicle_id VARCHAR(20) NOT NULL UNIQUE,
    vin CHAR(17) NOT NULL UNIQUE,
    make VARCHAR(60) NOT NULL,
    model VARCHAR(60) NOT NULL,
    model_year SMALLINT NOT NULL,
    body_type VARCHAR(30) NOT NULL,
    fuel_type VARCHAR(30) NOT NULL,
    color VARCHAR(30),
    vehicle_condition VARCHAR(10) NOT NULL,
    mileage_at_acquisition INTEGER NOT NULL,
    manufacturer_msrp NUMERIC(14, 2) NOT NULL,
    CONSTRAINT ck_dim_vehicle_year CHECK (model_year BETWEEN 1980 AND 2200),
    CONSTRAINT ck_dim_vehicle_condition CHECK (vehicle_condition IN ('New', 'Used')),
    CONSTRAINT ck_dim_vehicle_mileage CHECK (mileage_at_acquisition >= 0),
    CONSTRAINT ck_dim_vehicle_msrp CHECK (manufacturer_msrp >= 0)
);

CREATE TABLE IF NOT EXISTS analytics.dim_employee (
    employee_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id VARCHAR(20) NOT NULL,
    dealership_key BIGINT NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    role VARCHAR(40) NOT NULL,
    hire_date DATE NOT NULL,
    employment_status VARCHAR(10) NOT NULL,
    effective_from DATE NOT NULL DEFAULT DATE '1900-01-01',
    effective_to DATE NOT NULL DEFAULT DATE '9999-12-31',
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_dim_employee_version UNIQUE (employee_id, effective_from),
    CONSTRAINT fk_dim_employee_dealership FOREIGN KEY (dealership_key)
        REFERENCES analytics.dim_dealership (dealership_key),
    CONSTRAINT ck_dim_employee_role CHECK (
        role IN ('Sales Consultant', 'Service Advisor', 'Service Technician', 'Inventory Specialist', 'Manager')
    ),
    CONSTRAINT ck_dim_employee_status CHECK (employment_status IN ('Active', 'Inactive')),
    CONSTRAINT ck_dim_employee_effective_dates CHECK (effective_from <= effective_to)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_employee_current
    ON analytics.dim_employee (employee_id)
    WHERE is_current;

CREATE TABLE IF NOT EXISTS analytics.dim_service (
    service_key SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_type VARCHAR(50) NOT NULL UNIQUE,
    service_category VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

COMMIT;
