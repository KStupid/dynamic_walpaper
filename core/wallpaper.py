"""
wallpaper.py — Manages setting the desktop wallpaper via hyprctl/hyprpaper.

Uses subprocess to call:
    hyprctl hyprpaper wallpaper "MONITOR,PATH,cover"
"""

import os
import subprocess
import logging


logger = logging.getLogger(__name__)


class WallpaperManager:

    def __init__(self, monitor="eDP-1"):
        """
        Args:
            monitor: The Hyprland monitor name (e.g. "eDP-1").
        """
        self.monitor = monitor

    def set_wallpaper(self, path):
        """
        Set the wallpaper to the given image file.

        Args:
            path: Absolute path to the wallpaper image file.

        Returns:
            True if wallpaper was changed successfully, False otherwise.
        """

        # --- Validate the file exists ---
        if not os.path.isfile(path):
            logger.error(f"Wallpaper file does not exist: {path}")
            return False

        # --- Build the hyprctl command ---
        wallpaper_arg = f"{self.monitor},{path},cover"

        try:
            result = subprocess.run(
                ["hyprctl", "hyprpaper", "wallpaper", wallpaper_arg],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            logger.error("hyprctl command not found — is Hyprland installed?")
            return False
        except Exception as e:
            logger.error(f"Failed to run hyprctl: {e}")
            return False

        # --- Check for errors ---
        if result.returncode != 0:
            logger.error(
                f"hyprctl failed (exit code {result.returncode}): "
                f"{result.stderr.strip()}"
            )
            return False

        logger.info(f"Wallpaper changed successfully → {path}")
        return True