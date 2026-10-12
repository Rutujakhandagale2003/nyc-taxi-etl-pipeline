"""Extract step: download daily weather for one month from the Open-Meteo API."""
import json
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session() -> requests.Session:
    """A requests session that automatically retries on temporary server errors."""
    retry = Retry(
        total=3,
        backoff_factor=2,                       # waits 2s, 4s, 8s between retries
        status_forcelist=[429, 500, 502, 503, 504],
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def extract_weather(month: str, config: dict, logger) -> Path:
    """Call the weather API for one month and save the raw JSON response."""
    destination = config["paths"]["raw"] / "weather" / f"weather_{month}.json"
    if destination.exists():
        logger.info("Already downloaded, skipping: %s", destination.name)
        return destination

    period = pd.Period(month, freq="M")
    weather_cfg = config["weather"]
    params = {
        "latitude": weather_cfg["latitude"],
        "longitude": weather_cfg["longitude"],
        "start_date": period.start_time.strftime("%Y-%m-%d"),
        "end_date": period.end_time.strftime("%Y-%m-%d"),
        "daily": ",".join(weather_cfg["daily_variables"]),
        "timezone": weather_cfg["timezone"],
    }

    logger.info("Calling weather API for %s to %s", params["start_date"], params["end_date"])
    with build_session() as session:
        response = session.get(config["sources"]["weather_api_url"], params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

    if "daily" not in data:
        raise ValueError(f"Unexpected weather API response: {data}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info("Saved %s (%d days)", destination.name, len(data["daily"]["time"]))
    return destination