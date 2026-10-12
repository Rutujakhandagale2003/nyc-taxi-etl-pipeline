-- ================= DIMENSIONS =================
CREATE TABLE IF NOT EXISTS dim_zone (
    location_id    SMALLINT PRIMARY KEY,
    borough        VARCHAR,
    zone           VARCHAR,
    service_zone   VARCHAR
);

CREATE TABLE IF NOT EXISTS dim_payment_type (
    payment_type_id    TINYINT PRIMARY KEY,
    payment_type_name  VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER PRIMARY KEY,   -- e.g. 20240109
    full_date    DATE NOT NULL,
    year         SMALLINT,
    quarter      TINYINT,
    month        TINYINT,
    month_name   VARCHAR,
    day          TINYINT,
    day_name     VARCHAR,
    day_of_week  TINYINT,               -- 1 = Monday ... 7 = Sunday
    is_weekend   BOOLEAN
);

CREATE TABLE IF NOT EXISTS dim_weather (
    date_key            INTEGER PRIMARY KEY,
    temp_max_c          DOUBLE,
    temp_min_c          DOUBLE,
    temp_mean_c         DOUBLE,
    precipitation_mm    DOUBLE,
    rain_mm             DOUBLE,
    snowfall_cm         DOUBLE,
    wind_speed_max_kmh  DOUBLE,
    weather_category    VARCHAR
);

-- ================= FACT =================
-- Grain: one row per valid taxi trip
CREATE TABLE IF NOT EXISTS fact_trips (
    vendor_id              TINYINT,
    pickup_datetime        TIMESTAMP,
    dropoff_datetime       TIMESTAMP,
    pickup_date_key        INTEGER,     -- links to dim_date and dim_weather
    pickup_hour            TINYINT,
    pickup_location_id     SMALLINT,    -- links to dim_zone
    dropoff_location_id    SMALLINT,    -- links to dim_zone
    payment_type_id        TINYINT,     -- links to dim_payment_type
    rate_code_id           TINYINT,
    passenger_count        TINYINT,
    trip_distance          REAL,
    trip_duration_minutes  REAL,
    avg_speed_mph          REAL,
    fare_amount            DOUBLE,
    extra                  DOUBLE,
    mta_tax                DOUBLE,
    tip_amount             DOUBLE,
    tolls_amount           DOUBLE,
    improvement_surcharge  DOUBLE,
    congestion_surcharge   DOUBLE,
    airport_fee            DOUBLE,
    total_amount           DOUBLE,
    tip_pct                REAL,
    source_month           VARCHAR NOT NULL,   -- which monthly file this row came from
    loaded_at              TIMESTAMP DEFAULT current_timestamp
);

-- ================= AUDIT =================
CREATE TABLE IF NOT EXISTS etl_load_log (
    month        VARCHAR,
    taxi_type    VARCHAR,
    rows_loaded  BIGINT,
    loaded_at    TIMESTAMP DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS dq_results (
    run_at       TIMESTAMP,
    month        VARCHAR,
    check_name   VARCHAR,
    column_name  VARCHAR,
    severity     VARCHAR,
    failed_rows  BIGINT,
    passed       BOOLEAN,
    details      VARCHAR
);