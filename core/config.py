"""
config.py — Loads, validates, and writes the workspace-to-wallpaper configuration.

Reads config/config.toml from the project root. Expected shape:

    monitor = "eDP-1"        # optional; "auto" or missing → detected at startup

    [workspaces]
    "1" = "wallpapers/movie/workspace_1.jpg"
    "2" = "wallpapers/movie/workspace_2.jpg"

Wallpaper paths may be absolute or relative to the project root (the parent
of the config/ folder). The generator writes relative paths by default, so
the whole project folder stays portable between machines/accounts.
"""

import os
import sys
import logging
import tomllib


logger = logging.getLogger(__name__)


def project_root_from_config_path(config_path):
    """config/config.toml → project root is two levels up."""
    return os.path.dirname(os.path.dirname(os.path.abspath(config_path)))


def resolve_wallpaper_path(path, project_root):
    """Turn a config entry into an absolute path (relative → against project root)."""
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(project_root, path))


def format_toml_value(val) -> str:
    """Format a python value into a TOML literal."""
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    elif isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, list):
        items = ", ".join(format_toml_value(item) for item in val)
        return f"[{items}]"
    else:
        return f'"{val}"'


def load_raw_config(config_path):
    """Parse config.toml without validation; {} if missing/unreadable."""
    if not os.path.isfile(config_path):
        return {}
    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        logger.warning(f"Could not parse existing config.toml: {e}. Recreating...")
        return {}


def save_config(config_path, config):
    """
    Write a full config dict (top-level scalars + table sections) to TOML.

    Note: comments in the existing file are not preserved (TOML has no
    comment API in tomllib) — same behavior as the original generator.
    """
    top_level_scalars = {}
    sections = {}

    for key, val in config.items():
        if isinstance(val, dict):
            sections[key] = val
        else:
            top_level_scalars[key] = val

    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            # Top-level key-values first
            for k, v in top_level_scalars.items():
                f.write(f'"{k}" = {format_toml_value(v)}\n')
            if top_level_scalars:
                f.write("\n")

            # Then sections
            for section_name, section_dict in sections.items():
                f.write(f"[{section_name}]\n")
                for k, v in section_dict.items():
                    f.write(f'"{k}" = {format_toml_value(v)}\n')
                f.write("\n")
    except Exception as e:
        raise RuntimeError(f"Failed to write config file '{config_path}': {e}") from e


def persist_monitor(config_path, monitor):
    """Store the detected monitor as a top-level key so the user can edit it."""
    config = load_raw_config(config_path)
    config["monitor"] = monitor
    save_config(config_path, config)
    logger.info(f"Saved monitor '{monitor}' to config (edit it there anytime)")


def load_config(config_path):
    """
    Load the TOML config file and return the parsed configuration.

    Args:
        config_path: Absolute path to config.toml

    Returns:
        {
            "workspaces": { workspace_id_str: absolute_wallpaper_path, ... },
            "monitor": monitor_name_or_None,   # None → auto-detect at startup
        }

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

    # --- Monitor: string, "auto", or missing ---
    monitor = config.get("monitor")
    if monitor is not None and not isinstance(monitor, str):
        logger.warning(f"Ignoring non-string 'monitor' value: {monitor!r}")
        monitor = None
    if isinstance(monitor, str) and monitor.strip().lower() == "auto":
        monitor = None  # "auto" → detect at startup, never persisted over "auto"

    # --- Validate each mapping and resolve paths against the project root ---
    project_root = project_root_from_config_path(config_path)
    validated = {}

    for workspace_id, wallpaper_path in workspaces.items():

        # Check that the value is a string
        if not isinstance(wallpaper_path, str):
            logger.error(
                f"Workspace '{workspace_id}': wallpaper path must be a string, "
                f"got {type(wallpaper_path).__name__}"
            )
            sys.exit(1)

        absolute = resolve_wallpaper_path(wallpaper_path, project_root)

        # Check that the wallpaper file exists
        if not os.path.isfile(absolute):
            logger.warning(
                f"Workspace '{workspace_id}': wallpaper file does not exist: "
                f"{absolute}"
            )
            # Not fatal — the file might appear later, or user might fix config.
            # We still load it, but warn.

        validated[workspace_id] = absolute

    logger.info(f"Loaded {len(validated)} workspace mapping(s) from config")

    return {"workspaces": validated, "monitor": monitor}
