"""
config.py — Loads and validates the workspace-to-wallpaper configuration.

Reads config/config.toml from the project root.
Returns a dictionary of { workspace_id_string: wallpaper_path_string }.
"""

import os
import sys
import logging
import tomllib


logger = logging.getLogger(__name__)


def load_config(config_path):
    """
    Load the TOML config file and return the workspace mappings.

    Args:
        config_path: Absolute path to config.toml

    Returns:
        A dictionary like { "1": "/path/to/wallpaper.png", "2": "...", ... }

    Raises:
        SystemExit on fatal config errors.
    """

    # --- Check that the file exists ---
    if not os.path.isfile(config_path):
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    # --- Read and parse the TOML file ---
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        logger.error(f"Invalid TOML in config file: {e}")
        sys.exit(1)

    # --- Extract the [workspaces] section ---
    workspaces = config.get("workspaces")

    if workspaces is None:
        logger.error("Config file is missing the [workspaces] section")
        sys.exit(1)

    if not isinstance(workspaces, dict):
        logger.error("[workspaces] section must be a table of key = value pairs")
        sys.exit(1)

    if len(workspaces) == 0:
        logger.warning("No workspace mappings found in config file")

    # --- Validate each mapping ---
    validated = {}

    for workspace_id, wallpaper_path in workspaces.items():

        # Check that the value is a string
        if not isinstance(wallpaper_path, str):
            logger.error(
                f"Workspace '{workspace_id}': wallpaper path must be a string, "
                f"got {type(wallpaper_path).__name__}"
            )
            sys.exit(1)

        # Check that the wallpaper file exists
        if not os.path.isfile(wallpaper_path):
            logger.warning(
                f"Workspace '{workspace_id}': wallpaper file does not exist: "
                f"{wallpaper_path}"
            )
            # Not fatal — the file might appear later, or user might fix config.
            # We still load it, but warn.

        validated[workspace_id] = wallpaper_path

    logger.info(f"Loaded {len(validated)} workspace mapping(s) from config")

    return validated
