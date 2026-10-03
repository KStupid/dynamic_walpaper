"""
main.py — Dynamic Workspace Wallpaper: single-command entrypoint.

The one documented command (scans movies, generates wallpapers, updates
config, and starts the background listener):

    python main.py <location> <no_of_workspace>

<location> is a movie file OR a folder of movies.

Other modes:

    python main.py                                  # listener only, foreground
    python main.py --listen                         # same, explicit
    python main.py <location> <count> --foreground  # generate, then listen here
    python main.py <location> <count> --no-start    # generate only
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.toml")

_RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
PID_FILE = os.path.join(_RUNTIME_DIR, "dynamic-wallpaper.pid")
LOG_FILE = os.path.join(_RUNTIME_DIR, "dynamic-wallpaper.log")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# pid / background-daemon helpers
# ---------------------------------------------------------------------------

def read_pid():
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def write_pid(pid):
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except OSError as e:
        logger.warning(f"Could not write pid file {PID_FILE}: {e}")


def clear_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def pid_alive(pid):
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def stop_running_daemon():
    """
    Terminate a running daemon, if any. A freshly generated config only
    takes effect when the listener restarts, so we stop the old one first.
    Returns True when a daemon was actually stopped.
    """
    pid = read_pid()
    if not pid_alive(pid):
        if pid:
            clear_pid()  # stale pid file from a previous session
        return False

    logger.info(f"Stopping running wallpaper daemon (pid {pid}) to pick up the new config")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False

    for _ in range(20):  # up to ~2s
        if not pid_alive(pid):
            break
        time.sleep(0.1)
    else:
        logger.warning("Daemon did not exit in time — sending SIGKILL")
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        time.sleep(0.2)

    clear_pid()
    return True


def start_background_listener():
    """Spawn the listener detached from this terminal. Returns True on success."""
    stop_running_daemon()

    try:
        log_fh = open(LOG_FILE, "ab")
    except OSError as e:
        logger.error(f"Could not open log file {LOG_FILE}: {e}")
        return False

    try:
        process = subprocess.Popen(
            [sys.executable, os.path.join(PROJECT_ROOT, "main.py"), "--listen"],
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=log_fh,
            start_new_session=True,
            cwd=PROJECT_ROOT,
        )
    except OSError as e:
        logger.error(f"Could not start background listener: {e}")
        return False
    finally:
        log_fh.close()

    # Give the child a moment; a crash on startup (bad env, no Hyprland)
    # surfaces here instead of failing silently.
    time.sleep(0.7)
    if pid_alive(process.pid):
        logger.info(f"Wallpaper daemon running in background (pid {process.pid})")
        logger.info(f"Logs: {LOG_FILE}")
        return True

    logger.error(f"Background listener died immediately — check {LOG_FILE}")
    return False


# ---------------------------------------------------------------------------
# listener (foreground)
# ---------------------------------------------------------------------------

def run_listener():
    from core.config import load_config, persist_monitor
    from core.mapping import WorkspaceMapping
    from core.wallpaper import WallpaperManager, detect_monitor
    from platforms.hyprland import listen

    # --- Load config ---
    cfg = load_config(CONFIG_PATH)

    # --- Build the mapping ---
    mapping = WorkspaceMapping()
    for workspace_id, wallpaper_path in cfg["workspaces"].items():
        mapping.set(workspace_id, wallpaper_path)
        logger.info(f"  Workspace {workspace_id} → {wallpaper_path}")

    # --- Resolve the monitor (config → auto-detect → fallback) ---
    monitor = cfg["monitor"]
    if monitor is None:
        monitor = detect_monitor()
        if monitor is None:
            monitor = "eDP-1"
            logger.warning("Could not detect a monitor — falling back to 'eDP-1'")
        else:
            logger.info(f"Detected monitor: {monitor}")
        try:
            persist_monitor(CONFIG_PATH, monitor)
        except RuntimeError as e:
            logger.warning(f"Could not save monitor to config: {e}")
    else:
        logger.info(f"Using configured monitor: {monitor}")

    wallpaper_manager = WallpaperManager(monitor=monitor)

    # --- Mark ourselves as the running daemon ---
    write_pid(os.getpid())

    # Make SIGTERM (e.g. from a restart) shut down gracefully
    def _sigterm_to_interrupt(signum, frame):
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, _sigterm_to_interrupt)
    except (ValueError, OSError):
        pass  # can't set a handler here — non-fatal

    try:
        logger.info("Starting Hyprland workspace event listener...")
        listen(mapping, wallpaper_manager)
    finally:
        clear_pid()


# ---------------------------------------------------------------------------
# generation pipeline
# ---------------------------------------------------------------------------

def run_generation(args):
    from core.generator import generate_wallpapers

    logger.info(
        f"Generating wallpapers from {args.location} "
        f"for {args.count} workspace(s)"
    )

    try:
        mappings, _ = generate_wallpapers(
            args.location,
            args.count,
            output_dir=args.output_dir,
            seed=args.seed,
            project_root=PROJECT_ROOT,
            config_path=CONFIG_PATH,
        )
    except (RuntimeError, ValueError) as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"{len(mappings)} workspace(s) configured")


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("Dynamic Workspace Wallpaper — starting up")

    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Dynamic Workspace Wallpaper — random frames from the movies "
            "you've seen, as per-workspace wallpapers (Arch + Hyprland)."
        ),
        epilog=(
            "Examples:\n"
            "  python main.py ~/Movies 10            # folder of movies, 10 workspaces\n"
            "  python main.py movie.mp4 5            # single movie, 5 workspaces\n"
            "  python main.py                        # run listener only (foreground)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("location", nargs="?", help="Movie file or folder of movies")
    parser.add_argument(
        "count", nargs="?", type=int,
        help="Number of workspaces to map wallpapers to",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Where to save extracted frames (default: wallpapers/movie)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducible splits and timestamps",
    )
    parser.add_argument(
        "--listen", action="store_true",
        help="Skip generation; run the listener in the foreground",
    )
    parser.add_argument(
        "--foreground", action="store_true",
        help="After generating, run the listener in this terminal instead of the background",
    )
    parser.add_argument(
        "--no-start", action="store_true",
        help="Generate wallpapers and update config, but do not start the listener",
    )
    args = parser.parse_args()

    # --- Listener-only mode ---
    if args.listen or (args.location is None and args.count is None):
        if args.location or args.count:
            parser.error("provide BOTH <location> and <count> to generate, or neither to just listen")
        run_listener()
        return

    # --- Generation mode ---
    if args.location is None or args.count is None:
        parser.error("generation needs both <location> and <no_of_workspace>")
    if args.count <= 0:
        parser.error(f"workspace count must be a positive integer, got {args.count}")

    run_generation(args)

    if args.no_start:
        logger.info("Listener not started (--no-start). Start it later with: python main.py")
        return

    if args.foreground:
        run_listener()
        return

    if start_background_listener():
        print()
        print("To auto-start the listener on login, add this to hyprland.conf:")
        print(f"  exec-once = {sys.executable} {os.path.join(PROJECT_ROOT, 'main.py')} --listen")


if __name__ == "__main__":
    main()
