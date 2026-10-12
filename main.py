"""Entry point for the NYC Taxi ETL pipeline."""
import sys

from src.config import load_config
from src.extract.tlc import extract_trips, extract_zone_lookup
from src.logger import get_logger


def main():
    config = load_config()
    logger = get_logger("pipeline", config["paths"]["logs"])
    logger.info("Pipeline started")

    try:
        # ---------- EXTRACT ----------
        extract_zone_lookup(config, logger)
        for month in config["pipeline"]["months"]:
            extract_trips(month, config, logger)

        logger.info("Pipeline finished successfully")

    except Exception:
        logger.exception("Pipeline failed")  # logs the full error traceback
        sys.exit(1)  # non-zero exit code tells schedulers the run failed


if __name__ == "__main__":
    main()