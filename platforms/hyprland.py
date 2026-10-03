"""
hyprland.py — Hyprland platform backend.

Connects to the Hyprland IPC event socket and listens for workspace change
events. When a workspace change is detected, it looks up the wallpaper
from the mapping and tells the WallpaperManager to change it.

The socket is a byte stream, so we use a buffer to handle partial reads
and multiple events arriving in a single recv() call.
"""

import socket
import os
import sys
import logging


logger = logging.getLogger(__name__)


def get_socket_path():
    """
    Build the path to the Hyprland event socket (.socket2.sock).

    Returns:
        The full socket path string.

    Raises:
        SystemExit if required environment variables are missing.
    """

    xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not xdg_runtime_dir:
        logger.error("XDG_RUNTIME_DIR environment variable is not set")
        sys.exit(1)

    hyprland_instance = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not hyprland_instance:
        logger.error("HYPRLAND_INSTANCE_SIGNATURE environment variable is not set")
        sys.exit(1)

    socket_path = os.path.join(
        xdg_runtime_dir, "hypr", hyprland_instance, ".socket2.sock"
    )

    if not os.path.exists(socket_path):
        logger.error(f"Hyprland socket not found: {socket_path}")
        sys.exit(1)

    return socket_path


def listen(mapping, wallpaper_manager):
    """
    Connect to the Hyprland IPC event socket and listen for workspace changes.

    This function runs forever (until the socket closes or the program is killed).

    Args:
        mapping: A WorkspaceMapping object with .get(workspace_id) method.
        wallpaper_manager: A WallpaperManager object with .set_wallpaper(path) method.
    """

    socket_path = get_socket_path()

    logger.info(f"Connecting to Hyprland socket: {socket_path}")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    try:
        sock.connect(socket_path)
    except ConnectionRefusedError:
        logger.error(f"Connection refused to Hyprland socket: {socket_path}")
        sys.exit(1)
    except OSError as e:
        logger.error(f"Failed to connect to Hyprland socket: {e}")
        sys.exit(1)

    logger.info("Connected to Hyprland IPC — listening for workspace events...")

    # Buffer for handling partial/multiple events in a single recv()
    buffer = ""

    try:
        while True:

            data = sock.recv(4096)

            # Empty data means the socket was closed
            if not data:
                logger.warning("Hyprland socket closed — stopping listener")
                break

            # Append received bytes to the buffer
            buffer += data.decode()

            # Split on newlines — each complete line is one event
            events = buffer.split("\n")

            # The last element may be incomplete — keep it in the buffer
            buffer = events.pop()

            for event in events:

                # Only react to workspacev2 events
                if not event.startswith("workspacev2>>"):
                    continue

                # Extract workspace ID from "workspacev2>>ID,NAME"
                value = event.split(">>", 1)[1]
                workspace_id = value.split(",", 1)[0]

                logger.info(f"Workspace changed → {workspace_id}")

                # Look up the wallpaper for this workspace
                wallpaper = mapping.get(workspace_id)

                if wallpaper is None:
                    logger.warning(
                        f"No wallpaper mapped for workspace {workspace_id}"
                    )
                    continue

                logger.info(f"Wallpaper selected → {wallpaper}")

                # Change the wallpaper
                wallpaper_manager.set_wallpaper(wallpaper)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt — shutting down")
    finally:
        sock.close()
        logger.info("Socket closed")