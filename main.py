"""Entry point for the NYC Taxi ETL pipeline."""
import sys

from src.config import load_config
from src.extract.tlc import extract_trips, extract_zone_lookup
from src.extract.weather import extract_weather
from src.logger import get_logger
from src.transform.clean import transform_trips
from src.transform.enrich import enrich_trips
from src.transform.weather import transform_weather


def main():
    config = load_config()
    logger = get_logger("pipeline", config["paths"]["logs"])
    logger.info("Pipeline started")

    try:
        # ---------- EXTRACT (zone lookup, downloaded once) ----------
        zones_path = extract_zone_lookup(config, logger)

        for month in config["pipeline"]["months"]:
            logger.info("========== Processing month %s ==========", month)

            # ---------- EXTRACT ----------
            raw_trips_path = extract_trips(month, config, logger)
            raw_weather_path = extract_weather(month, config, logger)

            # ---------- TRANSFORM ----------
            clean_path = transform_trips(raw_trips_path, month, config, logger)
            weather_path = transform_weather(raw_weather_path, month, config, logger)
            enrich_trips(clean_path, weather_path, zones_path, month, config, logger)

        logger.info("Pipeline finished successfully")

    except Exception:
        logger.exception("Pipeline failed")
        sys.exit(1)


if __name__ == "__main__":
    main()