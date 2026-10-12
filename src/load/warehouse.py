"""Load step: write dimensions and facts into a DuckDB star schema."""
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from src.config import PROJECT_ROOT
from src.transform.enrich import PAYMENT_TYPES, load_zones

SCHEMA_FILE = PROJECT_ROOT / "sql" / "schema.sql"

FACT_COLUMNS = [
    "vendor_id", "pickup_datetime", "dropoff_datetime", "pickup_date_key", "pickup_hour",
    "pickup_location_id", "dropoff_location_id", "payment_type_id", "rate_code_id",
    "passenger_count", "trip_distance", "trip_duration_minutes", "avg_speed_mph",
    "fare_amount", "extra", "mta_tax", "tip_amount", "tolls_amount",
    "improvement_surcharge", "congestion_surcharge", "airport_fee", "total_amount",
    "tip_pct", "source_month",
]

WEATHER_COLUMNS = [
    "date_key", "temp_max_c", "temp_min_c", "temp_mean_c", "precipitation_mm",
    "rain_mm", "snowfall_cm", "wind_speed_max_kmh", "weather_category",
]


# ---------- Helpers ----------

def to_date_key(dates: pd.Series) -> pd.Series:
    """2024-01-09 -> 20240109 using fast arithmetic instead of slow string formatting."""
    return (dates.dt.year * 10000 + dates.dt.month * 100 + dates.dt.day).astype("int32")


def get_connection(config: dict) -> duckdb.DuckDBPyConnection:
    db_path = config["paths"]["warehouse"] / config["warehouse"]["db_file"]
    return duckdb.connect(str(db_path))


def insert_dataframe(con, table: str, df: pd.DataFrame, columns: list, mode: str = "INSERT"):
    """Insert a pandas DataFrame into a DuckDB table via Apache Arrow (fast, keeps nulls)."""
    con.register("src_df", pa.Table.from_pandas(df[columns], preserve_index=False))
    cols = ", ".join(columns)
    con.execute(f"{mode} INTO {table} ({cols}) SELECT {cols} FROM src_df")
    con.unregister("src_df")


# ---------- Schema and static dimensions ----------

def create_schema(con, logger):
    con.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    logger.info("Warehouse schema ready")


def load_static_dimensions(con, zones_path: Path, logger):
    """Dimensions that don't depend on the month: zones and payment types (upsert)."""
    zones = load_zones(zones_path)
    for col in ["borough", "zone", "service_zone"]:
        zones[col] = zones[col].astype("string")
    insert_dataframe(con, "dim_zone", zones,
                     ["location_id", "borough", "zone", "service_zone"], mode="INSERT OR REPLACE")

    # Code 0 appears in the data but isn't in the official list, so we add it as unknown.
    # Without it, ~4% of trips would disappear from any report that joins to this table!
    payments = {0: "unknown", **PAYMENT_TYPES}
    payment_df = pd.DataFrame({"payment_type_id": list(payments.keys()),
                               "payment_type_name": list(payments.values())})
    insert_dataframe(con, "dim_payment_type", payment_df,
                     ["payment_type_id", "payment_type_name"], mode="INSERT OR REPLACE")

    logger.info("Loaded dim_zone (%d rows) and dim_payment_type (%d rows)", len(zones), len(payment_df))


# ---------- Monthly load ----------

def build_dim_date(month: str) -> pd.DataFrame:
    dates = pd.Series(pd.date_range(f"{month}-01", periods=pd.Period(month).days_in_month, freq="D"))
    return pd.DataFrame({
        "date_key": to_date_key(dates),
        "full_date": dates.dt.date,
        "year": dates.dt.year,
        "quarter": dates.dt.quarter,
        "month": dates.dt.month,
        "month_name": dates.dt.month_name(),
        "day": dates.dt.day,
        "day_name": dates.dt.day_name(),
        "day_of_week": dates.dt.dayofweek + 1,
        "is_weekend": dates.dt.dayofweek >= 5,
    })


def build_fact(enriched_path: Path, month: str) -> pd.DataFrame:
    # Read ONLY the columns we need: Parquet is columnar, so this skips the rest on disk
    needed = [c for c in FACT_COLUMNS if c not in ("pickup_date_key", "payment_type_id", "source_month")]
    df = pd.read_parquet(enriched_path, columns=needed + ["pickup_date", "payment_type"])
    df["pickup_date_key"] = to_date_key(df["pickup_date"])
    df = df.rename(columns={"payment_type": "payment_type_id"})
    df["source_month"] = month
    return df


def load_dq_results(con, month: str, config: dict):
    taxi_type = config["sources"]["taxi_type"]
    report = pd.read_csv(config["paths"]["quality"] / f"dq_results_{taxi_type}_{month}.csv")
    report = report.rename(columns={"column": "column_name"})
    report["run_at"] = pd.to_datetime(report["run_at"])
    report["details"] = report["details"].fillna("").astype("string")
    con.execute("DELETE FROM dq_results WHERE month = ?", [month])
    insert_dataframe(con, "dq_results", report,
                     ["run_at", "month", "check_name", "column_name", "severity",
                      "failed_rows", "passed", "details"])


def verify_month_load(con, month: str, expected_rows: int, logger):
    """Reconciliation: correct row count and no orphan keys."""
    loaded = con.execute("SELECT COUNT(*) FROM fact_trips WHERE source_month = ?", [month]).fetchone()[0]
    if loaded != expected_rows:
        raise ValueError(f"Row count mismatch for {month}: expected {expected_rows:,}, loaded {loaded:,}")

    orphans = con.execute("""
        SELECT
            COUNT(*) FILTER (WHERE pz.location_id IS NULL)     AS missing_pickup_zone,
            COUNT(*) FILTER (WHERE dz.location_id IS NULL)     AS missing_dropoff_zone,
            COUNT(*) FILTER (WHERE p.payment_type_id IS NULL)  AS missing_payment_type,
            COUNT(*) FILTER (WHERE d.date_key IS NULL)         AS missing_date,
            COUNT(*) FILTER (WHERE w.date_key IS NULL)         AS missing_weather
        FROM fact_trips f
        LEFT JOIN dim_zone pz         ON f.pickup_location_id  = pz.location_id
        LEFT JOIN dim_zone dz         ON f.dropoff_location_id = dz.location_id
        LEFT JOIN dim_payment_type p  ON f.payment_type_id     = p.payment_type_id
        LEFT JOIN dim_date d          ON f.pickup_date_key     = d.date_key
        LEFT JOIN dim_weather w       ON f.pickup_date_key     = w.date_key
        WHERE f.source_month = ?
    """, [month]).fetchone()

    if any(orphans):
        raise ValueError(f"Orphan keys found for {month}: {orphans}")
    logger.info("Verified %s: %s rows, no orphan keys", month, f"{loaded:,}")


def load_month(con, enriched_path: Path, weather_path: Path, month: str, config: dict, logger):
    logger.info("Loading %s into the warehouse", month)

    dim_date = build_dim_date(month)
    weather = pd.read_parquet(weather_path)
    weather["date_key"] = to_date_key(weather["weather_date"])
    fact = build_fact(enriched_path, month)

    con.begin()  # everything below succeeds together or not at all
    try:
        insert_dataframe(con, "dim_date", dim_date, list(dim_date.columns), mode="INSERT OR REPLACE")
        insert_dataframe(con, "dim_weather", weather, WEATHER_COLUMNS, mode="INSERT OR REPLACE")

        # Idempotent fact load: remove this month's old rows, then insert the new ones
        con.execute("DELETE FROM fact_trips WHERE source_month = ?", [month])
        insert_dataframe(con, "fact_trips", fact, FACT_COLUMNS)

        con.execute("INSERT INTO etl_load_log (month, taxi_type, rows_loaded) VALUES (?, ?, ?)",
                    [month, config["sources"]["taxi_type"], len(fact)])
        load_dq_results(con, month, config)

        verify_month_load(con, month, len(fact), logger)
        con.commit()
    except Exception:
        con.rollback()
        logger.error("Load for %s rolled back", month)
        raise

    logger.info("Loaded %s rows into fact_trips for %s", f"{len(fact):,}", month)