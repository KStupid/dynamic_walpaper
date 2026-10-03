"""
main.py — Entry point for Dynamic Workspace Wallpaper.

This script:
1. Sets up logging
2. Loads the config file (config/config.toml)
3. Creates the workspace-to-wallpaper mapping
4. Creates the wallpaper manager
5. Starts the Hyprland event listener
"""

import os
import sys
import logging

from core.config import load_config
from core.mapping import WorkspaceMapping
from core.wallpaper import WallpaperManager
from platforms.hyprland import listen


def main():

    # --- Set up logging ---
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    logger = logging.getLogger(__name__)

    logger.info("Dynamic Workspace Wallpaper — starting up")

    # --- Find the config file ---
    # config.toml lives in config/ relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config", "config.toml")

    # --- Load config ---
    workspace_wallpapers = load_config(config_path)

    # --- Build the mapping ---
    mapping = WorkspaceMapping()

    for workspace_id, wallpaper_path in workspace_wallpapers.items():
        mapping.set(workspace_id, wallpaper_path)
        logger.info(f"  Workspace {workspace_id} → {wallpaper_path}")

    # --- Create the wallpaper manager ---
    wallpaper_manager = WallpaperManager(monitor="eDP-1")

    # --- Start listening for workspace changes ---
    logger.info("Starting Hyprland workspace event listener...")
    listen(mapping, wallpaper_manager)


if __name__ == "__main__":
    main()