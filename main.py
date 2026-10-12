"""Entry point for the NYC Taxi ETL pipeline."""
from src.config import load_config
from src.logger import get_logger


def main():
    config = load_config()
    logger = get_logger("pipeline", config["paths"]["logs"])

    logger.info("Pipeline started")
    logger.info("Months to process: %s", config["pipeline"]["months"])
    logger.info("Raw data folder: %s", config["paths"]["raw"])
    logger.info("Pipeline finished successfully")


if __name__ == "__main__":
    main()