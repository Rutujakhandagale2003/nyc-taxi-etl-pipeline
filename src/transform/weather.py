"""Transform step: convert raw weather JSON into a clean daily table."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

COLUMN_RENAMES = {
    "time": "weather_date",
    "temperature_2m_max": "temp_max_c",
    "temperature_2m_min": "temp_min_c",
    "temperature_2m_mean": "temp_mean_c",
    "precipitation_sum": "precipitation_mm",
    "rain_sum": "rain_mm",
    "snowfall_sum": "snowfall_cm",
    "wind_speed_10m_max": "wind_speed_max_kmh",
}


def transform_weather(raw_path: Path, month: str, config: dict, logger) -> Path:
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # The useful part of the JSON is "daily": {"time": [...], "temperature_2m_max": [...], ...}
    df = pd.DataFrame(data["daily"])
    df = df.rename(columns=COLUMN_RENAMES)
    df["weather_date"] = pd.to_datetime(df["weather_date"])

    # ----- Validation: exactly one row per day, no missing days -----
    expected_days = pd.Period(month, freq="M").days_in_month
    if len(df) != expected_days:
        raise ValueError(f"Expected {expected_days} weather days for {month}, got {len(df)}")
    if df["weather_date"].duplicated().any():
        raise ValueError(f"Duplicate weather dates found for {month}")

    null_counts = df.isna().sum()
    if null_counts.any():
        logger.warning("Weather has missing values:\n%s", null_counts[null_counts > 0])

    # ----- Business-friendly category for each day -----
    heavy_rain = config["weather"]["heavy_rain_mm"]
    df["weather_category"] = np.select(
        [
            df["snowfall_cm"] > 0,
            df["precipitation_mm"] >= heavy_rain,
            df["precipitation_mm"] > 0,
        ],
        ["snow", "heavy_rain", "rain"],
        default="dry",
    )

    logger.info("Weather %s: %s", month, df["weather_category"].value_counts().to_dict())

    out_path = config["paths"]["staging"] / "weather" / f"weather_{month}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Saved %s", out_path.name)
    return out_path