"""Transform step 2: add time features and trip metrics, then join zones and weather."""
from pathlib import Path

import pandas as pd

# Official TLC payment type codes
PAYMENT_TYPES = {
    1: "credit_card",
    2: "cash",
    3: "no_charge",
    4: "dispute",
    5: "unknown",
    6: "voided",
}


def memory_mb(df: pd.DataFrame) -> float:
    return df.memory_usage(deep=True).sum() / (1024 * 1024)


def load_zones(zones_path: Path) -> pd.DataFrame:
    # keep_default_na=False stops pandas from turning text like "N/A" into missing values
    zones = pd.read_csv(zones_path, keep_default_na=False, na_values=[""])
    zones = zones.rename(columns={
        "LocationID": "location_id",
        "Borough": "borough",
        "Zone": "zone",
    })
    zones["location_id"] = zones["location_id"].astype("int16")
    for col in ["borough", "zone", "service_zone"]:
        zones[col] = zones[col].astype("category")

    if zones["location_id"].duplicated().any():
        raise ValueError("Duplicate location_id in zone lookup")
    return zones


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    pickup = df["pickup_datetime"]
    df["pickup_date"] = pickup.dt.normalize()            # date at midnight, still datetime64
    df["pickup_hour"] = pickup.dt.hour.astype("int8")
    df["pickup_day_name"] = pickup.dt.day_name().astype("category")
    df["is_weekend"] = pickup.dt.dayofweek >= 5          # Saturday=5, Sunday=6
    df["time_of_day"] = pd.cut(
        df["pickup_hour"],
        bins=[-1, 5, 11, 16, 20, 23],
        labels=["night", "morning", "afternoon", "evening", "late_evening"],
    )
    return df


def add_trip_metrics(df: pd.DataFrame) -> pd.DataFrame:
    hours = df["trip_duration_minutes"] / 60
    df["avg_speed_mph"] = (df["trip_distance"] / hours).astype("float32")

    df["payment_type_name"] = (
        df["payment_type"].map(PAYMENT_TYPES).fillna("unknown").astype("category")
    )

    # Cash tips are not recorded in this dataset, so tip % only makes sense for card payments
    is_card = df["payment_type"] == 1
    df["tip_pct"] = (df["tip_amount"] / df["fare_amount"] * 100).where(is_card).astype("float32")
    return df


def add_zone_names(df: pd.DataFrame, zones: pd.DataFrame, logger) -> pd.DataFrame:
    """Join zone names twice: once for pickup, once for dropoff."""
    for prefix in ["pickup", "dropoff"]:
        zone_cols = zones.rename(columns={
            "location_id": f"{prefix}_location_id",
            "borough": f"{prefix}_borough",
            "zone": f"{prefix}_zone",
            "service_zone": f"{prefix}_service_zone",
        })
        rows_before = len(df)
        df = df.merge(
            zone_cols,
            on=f"{prefix}_location_id",
            how="left",
            validate="many_to_one",   # fails loudly if the zone table has duplicate IDs
            indicator=True,           # adds a _merge column showing which rows matched
        )
        assert len(df) == rows_before, f"Row count changed after {prefix} zone join!"

        unmatched = int((df["_merge"] == "left_only").sum())
        if unmatched:
            logger.warning("%s rows have a %s location not in the zone table", f"{unmatched:,}", prefix)
        df = df.drop(columns="_merge")
    return df


def add_weather(df: pd.DataFrame, weather: pd.DataFrame, logger) -> pd.DataFrame:
    weather = weather[["weather_date", "weather_category", "temp_mean_c",
                       "precipitation_mm", "snowfall_cm"]].copy()
    weather["weather_date"] = weather["weather_date"].astype(df["pickup_date"].dtype)
    weather["weather_category"] = weather["weather_category"].astype("category")

    rows_before = len(df)
    df = df.merge(
        weather,
        left_on="pickup_date",
        right_on="weather_date",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    assert len(df) == rows_before, "Row count changed after weather join!"

    unmatched = int((df["_merge"] == "left_only").sum())
    if unmatched:
        logger.warning("%s trips have no matching weather day", f"{unmatched:,}")
    return df.drop(columns=["weather_date", "_merge"])


def enrich_trips(clean_path: Path, weather_path: Path, zones_path: Path,
                 month: str, config: dict, logger) -> Path:
    logger.info("Enriching %s", clean_path.name)

    df = pd.read_parquet(clean_path)
    weather = pd.read_parquet(weather_path)
    zones = load_zones(zones_path)

    df = add_time_features(df)
    df = add_trip_metrics(df)
    df = add_zone_names(df, zones, logger)
    df = add_weather(df, weather, logger)

    logger.info("Enriched %s rows, %d columns, memory %.1f MB",
                f"{len(df):,}", df.shape[1], memory_mb(df))

    taxi_type = config["sources"]["taxi_type"]
    out_path = config["paths"]["staging"] / "enriched" / f"enriched_{taxi_type}_{month}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Saved %s", out_path.name)
    return out_path