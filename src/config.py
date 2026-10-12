"""Loads the YAML config and resolves all paths relative to the project root."""
from pathlib import Path

import yaml

# Project root = the folder that contains this "src" folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "config.yaml"


def load_config(config_file: Path = CONFIG_FILE) -> dict:
    """Read config.yaml, convert paths to absolute Path objects, and create folders."""
    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Turn relative paths into absolute paths and make sure the folders exist
    for name, relative_path in config["paths"].items():
        full_path = PROJECT_ROOT / relative_path
        full_path.mkdir(parents=True, exist_ok=True)
        config["paths"][name] = full_path

    return config