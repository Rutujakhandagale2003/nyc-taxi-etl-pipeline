"""Extract step: download raw files from the NYC TLC website."""
import time
from pathlib import Path

import requests

CHUNK_SIZE = 1024 * 1024  # download 1 MB at a time


def download_file(url: str, destination: Path, logger, retries: int = 3, timeout: int = 60) -> Path:
    """Download a file with retries. Skips the download if the file already exists."""
    if destination.exists():
        logger.info("Already downloaded, skipping: %s", destination.name)
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_file = destination.with_suffix(destination.suffix + ".part")

    for attempt in range(1, retries + 1):
        try:
            logger.info("Downloading %s (attempt %d/%d)", url, attempt, retries)
            with requests.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()  # raises an error for 404, 500, etc.
                with open(temp_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        f.write(chunk)

            temp_file.replace(destination)  # rename only after a complete download
            size_mb = destination.stat().st_size / (1024 * 1024)
            logger.info("Saved %s (%.1f MB)", destination.name, size_mb)
            return destination

        except requests.RequestException as error:
            logger.warning("Download failed: %s", error)
            if temp_file.exists():
                temp_file.unlink()  # remove the incomplete file
            if attempt == retries:
                raise
            time.sleep(5 * attempt)  # wait longer after each failure


def extract_trips(month: str, config: dict, logger) -> Path:
    """Download one month of taxi trips, e.g. month='2024-01'."""
    taxi_type = config["sources"]["taxi_type"]
    file_name = f"{taxi_type}_tripdata_{month}.parquet"
    url = f"{config['sources']['trips_base_url']}/{file_name}"
    destination = config["paths"]["raw"] / "trips" / file_name
    return download_file(url, destination, logger)


def extract_zone_lookup(config: dict, logger) -> Path:
    """Download the taxi zone lookup CSV (maps LocationID to borough and zone name)."""
    url = config["sources"]["zone_lookup_url"]
    destination = config["paths"]["raw"] / "zones" / "taxi_zone_lookup.csv"
    return download_file(url, destination, logger)