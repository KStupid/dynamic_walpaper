"""
generate_movie_wallpapers.py — standalone CLI for the wallpaper generator.

Kept for compatibility — the documented single command is now:

    python main.py <location> <no_of_workspace>

Usage:
    python tools/generate_movie_wallpapers.py <movie_or_folder> <workspace_count> [--output-dir DIR] [--seed SEED]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.generator import generate_wallpapers


def main():
    parser = argparse.ArgumentParser(
        description="Generate workspace wallpapers from movie frames."
    )
    parser.add_argument(
        "location", type=str,
        help="Path to a movie/video file OR a folder of movies",
    )
    parser.add_argument(
        "workspace_count", type=int,
        help="Number of workspaces to generate wallpapers for",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory to save extracted wallpapers (default: wallpapers/movie)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducible splits and timestamps",
    )

    args = parser.parse_args()

    project_root = str(Path(__file__).resolve().parent.parent)

    try:
        mappings, _ = generate_wallpapers(
            args.location,
            args.workspace_count,
            output_dir=args.output_dir,
            seed=args.seed,
            project_root=project_root,
        )
    except (RuntimeError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    print()
    print(f"✓ {len(mappings)} workspace(s) configured")
    print("Start the listener with: python main.py")


if __name__ == "__main__":
    main()
