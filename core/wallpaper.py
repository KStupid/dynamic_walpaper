"""
wallpaper.py — Manages setting the desktop wallpaper via hyprctl/hyprpaper.

hyprpaper paints images it has in memory, so the correct protocol is:

    hyprctl hyprpaper preload <path>                 # decode into hyprpaper RAM
    hyprctl hyprpaper wallpaper "MONITOR,PATH,cover" # paint on a monitor

`preload` is skipped when the image is already loaded (checked via
`hyprctl hyprpaper listloaded`) to keep workspace switches instant after
the first visit.
"""

import json
import os
import subprocess
import logging


logger = logging.getLogger(__name__)


def detect_monitor():
    """
    Return the name of the first Hyprland monitor via `hyprctl monitors -j`,
    or None if it cannot be detected (hyprctl missing, not in a session, ...).
    """
    try:
        result = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    try:
        monitors = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    for mon in monitors:
        name = mon.get("name")
        if name:
            return name
    return None


class WallpaperManager:

    def __init__(self, monitor="eDP-1"):
        """
        Args:
            monitor: The Hyprland monitor name (e.g. "eDP-1").
        """
        self.monitor = monitor

    def _hyprctl(self, args):
        """
        Run a hyprctl subcommand.

        Returns:
            (ok, output) where ok is True when the exit code was 0.
        """
        try:
            result = subprocess.run(
                ["hyprctl", *args],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError:
            return False, "hyprctl command not found — is Hyprland installed?"
        except subprocess.TimeoutExpired:
            return False, f"hyprctl {' '.join(args)} timed out"
        except OSError as e:
            return False, f"Failed to run hyprctl: {e}"

        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output.strip()

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

        # --- Preload the image if hyprpaper doesn't have it in memory ---
        loaded_ok, loaded_out = self._hyprctl(["hyprpaper", "listloaded"])
        if not (loaded_ok and path in loaded_out):
            preload_ok, preload_out = self._hyprctl(["hyprpaper", "preload", path])
            if not preload_ok:
                # Non-fatal: hyprpaper may complain about double-preload or
                # the image may already be loaded under a slightly different
                # path string. The `wallpaper` call below decides success.
                logger.debug(f"hyprpaper preload reported: {preload_out}")

        # --- Apply it to the monitor ---
        wallpaper_arg = f"{self.monitor},{path},cover"

        ok, output = self._hyprctl(["hyprpaper", "wallpaper", wallpaper_arg])
        if not ok:
            logger.error(f"hyprctl hyprpaper wallpaper failed: {output}")
            return False

        logger.info(f"Wallpaper changed successfully → {path}")
        return True
