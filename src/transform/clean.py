"""Transform step 1: standardize, optimize memory, fix values, and split valid vs rejected rows."""
from pathlib import Path

import numpy as np
import pandas as pd

COLUMN_RENAMES = {
    "VendorID": "vendor_id",
    "tpep_pickup_datetime": "pickup_datetime",
    "tpep_dropoff_datetime": "dropoff_datetime",
    "RatecodeID": "rate_code_id",
    "PULocationID": "pickup_location_id",
    "DOLocationID": "dropoff_location_id",
    "Airport_fee": "airport_fee",
}

# Smaller data types save a lot of memory.
# Money columns stay float64 on purpose: float32 loses precision when summing millions of fares.
DTYPES = {
    "vendor_id": "int8",
    "passenger_count": "Int8",        # capital "I" = nullable integer (allows missing values)
    "rate_code_id": "Int8",
    "store_and_fwd_flag": "category",
    "pickup_location_id": "int16",
    "dropoff_location_id": "int16",
    "payment_type": "int8",
    "trip_distance": "float32",
}


def memory_mb(df: pd.DataFrame) -> float:
    return df.memory_usage(deep=True).sum() / (1024 * 1024)


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to consistent snake_case names."""
    df = df.rename(columns=COLUMN_RENAMES)
    df.columns = [col.lower() for col in df.columns]
    return df


def optimize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    return df.astype(DTYPES)


def add_trip_duration(df: pd.DataFrame) -> pd.DataFrame:
    duration = df["dropoff_datetime"] - df["pickup_datetime"]
    df["trip_duration_minutes"] = (duration.dt.total_seconds() / 60).astype("float32")
    return df


def fix_values(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Turn invalid-but-harmless values into 'unknown' (null) instead of dropping the row."""
    zero_passengers = df["passenger_count"].eq(0).fillna(False)
    df.loc[zero_passengers, "passenger_count"] = pd.NA

    bad_rate_code = df["rate_code_id"].notna() & ~df["rate_code_id"].isin(rules["valid_rate_codes"])
    df.loc[bad_rate_code, "rate_code_id"] = pd.NA
    return df


def build_rejection_checks(df: pd.DataFrame, month: str, rules: dict) -> dict:
    """Each rule returns True for rows that FAIL the rule."""
    month_start = pd.Timestamp(f"{month}-01")
    month_end = month_start + pd.offsets.MonthBegin(1)

    return {
        "pickup_outside_month": ~df["pickup_datetime"].between(month_start, month_end, inclusive="left"),
        "non_positive_duration": df["trip_duration_minutes"] <= 0,
        "duration_too_long": df["trip_duration_minutes"] > rules["max_trip_duration_minutes"],
        "distance_too_short": df["trip_distance"] < rules["min_trip_distance"],
        "distance_too_long": df["trip_distance"] > rules["max_trip_distance"],
        "fare_not_positive": df["fare_amount"] <= 0,
        "fare_too_high": df["fare_amount"] > rules["max_fare"],
        "too_many_passengers": (df["passenger_count"] > rules["max_passenger_count"]).fillna(False),
        "speed_too_high": (df["trip_distance"] / (df["trip_duration_minutes"] / 60)) > rules["max_avg_speed_mph"],
    }


def split_valid_and_rejected(df: pd.DataFrame, month: str, rules: dict, logger):
    checks = build_rejection_checks(df, month, rules)

    # Log how many rows fail each rule (a row can fail more than one)
    for rule_name, failed in checks.items():
        logger.info("  Rule %-24s failed rows: %s", rule_name, f"{int(failed.sum()):,}")

    # Each rejected row gets the FIRST rule it failed as its reason
    conditions = [np.asarray(failed, dtype=bool) for failed in checks.values()]
    reasons = np.select(conditions, list(checks.keys()), default="")

    is_rejected = reasons != ""
    valid = df[~is_rejected].copy()
    rejected = df[is_rejected].copy()
    rejected["reject_reason"] = reasons[is_rejected]
    return valid, rejected


def transform_trips(raw_path: Path, month: str, config: dict, logger) -> Path:
    """Full cleaning step for one month. Writes clean and rejected files to staging."""
    rules = config["cleaning"]
    logger.info("Transforming %s", raw_path.name)

    df = pd.read_parquet(raw_path)
    rows_in = len(df)
    logger.info("Read %s rows, memory %.1f MB", f"{rows_in:,}", memory_mb(df))

    df = standardize_columns(df)
    df = optimize_dtypes(df)
    logger.info("After dtype optimization: memory %.1f MB", memory_mb(df))

    df = add_trip_duration(df)
    df = fix_values(df, rules)
    valid, rejected = split_valid_and_rejected(df, month, rules, logger)

    # Data reconciliation: no row should ever be lost silently
    assert len(valid) + len(rejected) == rows_in, "Row count mismatch after cleaning!"

    reject_pct = 100 * len(rejected) / rows_in
    logger.info("Valid rows: %s | Rejected rows: %s (%.2f%%)",
                f"{len(valid):,}", f"{len(rejected):,}", reject_pct)

    taxi_type = config["sources"]["taxi_type"]
    staging = config["paths"]["staging"]
    clean_path = staging / "trips" / f"clean_{taxi_type}_{month}.parquet"
    rejected_path = staging / "rejected" / f"rejected_{taxi_type}_{month}.parquet"
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path.parent.mkdir(parents=True, exist_ok=True)

    valid.to_parquet(clean_path, index=False)
    rejected.to_parquet(rejected_path, index=False)
    logger.info("Saved %s and %s", clean_path.name, rejected_path.name)
    return clean_path