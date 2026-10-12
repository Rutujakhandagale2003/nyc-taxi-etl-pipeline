"""Logging setup: writes logs to both the terminal and a daily log file."""
import logging
from datetime import datetime
from pathlib import Path


def get_logger(name: str, log_dir: Path) -> logging.Logger:
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if get_logger is called more than once
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1) Show logs in the terminal
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 2) Save logs to a file, one file per day
    log_file = log_dir / f"pipeline_{datetime.now():%Y%m%d}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger