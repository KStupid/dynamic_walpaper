"""
generate_movie_wallpapers.py — Movie wallpaper generator tool.

Extracts random frames from a movie using FFmpeg and updates config/config.toml
to assign those frames as workspace wallpapers.

Usage:
    python tools/generate_movie_wallpapers.py <movie_path> <workspace_count> [--output-dir DIR] [--seed SEED]
"""

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS format."""
    total_seconds = int(math.floor(max(0.0, seconds)))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def check_dependencies():
    """Verify ffmpeg and ffprobe are installed."""
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("ffprobe"):
        missing.append("ffprobe")

    if missing:
        missing_str = ", ".join(missing)
        print(f"Error: Required tool(s) missing: {missing_str}")
        print("Please install FFmpeg on your system.")
        print("For Arch Linux, run: sudo pacman -S ffmpeg")
        sys.exit(1)


def get_video_duration(movie_path: str) -> float:
    """Extract video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        movie_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print("Error: ffprobe executable not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to execute ffprobe: {e}")
        sys.exit(1)

    if result.returncode != 0:
        print(f"Error: ffprobe failed to read video file: '{movie_path}'")
        stderr_msg = result.stderr.strip()
        if stderr_msg:
            print(f"Details: {stderr_msg}")
        sys.exit(1)

    output = result.stdout.strip()
    try:
        duration = float(output)
        if duration <= 0:
            print(f"Error: Video duration is non-positive ({duration}s).")
            sys.exit(1)
        return duration
    except ValueError:
        print(f"Error: Could not parse video duration from ffprobe output: '{output}'")
        sys.exit(1)


def generate_timestamps(duration: float, count: int, seed: int | None = None) -> list[float]:
    """
    Generate unique random timestamps spread across the video duration.
    """
    if seed is not None:
        random.seed(seed)

    # Avoid selecting frames extremely close to the beginning or end of long movies.
    # For short videos, use the full duration range.
    if duration >= 10.0:
        start_sec = max(1.0, duration * 0.05)
        end_sec = min(duration - 1.0, duration * 0.95)
    else:
        start_sec = 0.0
        end_sec = duration

    if end_sec <= start_sec:
        start_sec = 0.0
        end_sec = duration

    available_range = end_sec - start_sec
    bucket_width = available_range / count

    if bucket_width < 0.05 and count > 1:
        print(
            f"Notice: Workspace count ({count}) is high relative to video duration "
            f"({duration:.2f}s). Frames will be closely spaced."
        )

    timestamps = []
    for i in range(count):
        t_min = start_sec + i * bucket_width
        t_max = start_sec + (i + 1) * bucket_width

        if t_max > end_sec:
            t_max = end_sec

        if t_max <= t_min:
            ts = t_min
        else:
            ts = random.uniform(t_min, t_max)

        timestamps.append(round(ts, 3))

    return timestamps


def extract_frame(movie_path: str, timestamp: float, output_file: str):
    """Extract a single video frame at timestamp using ffmpeg."""
    cmd = [
        "ffmpeg",
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        movie_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-y",
        output_file,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print("Error: ffmpeg executable not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to execute ffmpeg: {e}")
        sys.exit(1)

    if result.returncode != 0 or not os.path.isfile(output_file):
        print(f"Error: FFmpeg failed to extract frame at {timestamp:.2f}s")
        stderr_msg = result.stderr.strip()
        if stderr_msg:
            print(f"Details: {stderr_msg}")
        sys.exit(1)


def format_toml_value(val) -> str:
    """Format a python value into TOML representation."""
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


def update_config_toml(config_path: str, workspace_mappings: dict[str, str]):
    """
    Update config/config.toml [workspaces] section while preserving any existing sections.
    """
    existing_config = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "rb") as f:
                existing_config = tomllib.load(f)
        except Exception as e:
            print(f"Warning: Could not parse existing config.toml: {e}. Recreating...")
            existing_config = {}

    # Replace [workspaces] table cleanly
    existing_config["workspaces"] = workspace_mappings

    # Separate top-level scalars and sections
    top_level_scalars = {}
    sections = {}

    for key, val in existing_config.items():
        if isinstance(val, dict):
            sections[key] = val
        else:
            top_level_scalars[key] = val

    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            # Write top-level key-values first
            for k, v in top_level_scalars.items():
                f.write(f'"{k}" = {format_toml_value(v)}\n')
            if top_level_scalars:
                f.write("\n")

            # Write sections
            for section_name, section_dict in sections.items():
                f.write(f"[{section_name}]\n")
                for k, v in section_dict.items():
                    f.write(f'"{k}" = {format_toml_value(v)}\n')
                f.write("\n")
    except Exception as e:
        print(f"Error: Failed to write config file '{config_path}': {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate workspace wallpapers from movie frames."
    )
    parser.add_argument("movie_path", type=str, help="Path to the movie/video file")
    parser.add_argument(
        "workspace_count", type=int, help="Number of workspaces to generate wallpapers for"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save extracted wallpapers (default: wallpapers/movie)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducible timestamps"
    )

    args = parser.parse_args()

    # 1. Validate dependencies
    check_dependencies()

    # 2. Validate inputs
    movie_path = os.path.abspath(args.movie_path)
    if not os.path.exists(movie_path):
        print(f"Error: Movie file does not exist: '{args.movie_path}'")
        sys.exit(1)

    if not os.path.isfile(movie_path):
        print(f"Error: Movie path is not a file: '{args.movie_path}'")
        sys.exit(1)

    if args.workspace_count <= 0:
        print(f"Error: Workspace count must be a positive integer, got {args.workspace_count}")
        sys.exit(1)

    # Resolve project root (parent directory of 'tools/')
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        output_dir = project_root / "wallpapers" / "movie"

    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"Error: Failed to create output directory '{output_dir}': {e}")
        sys.exit(1)

    # 3. Get video duration
    duration = get_video_duration(movie_path)

    print(f"Movie: {movie_path}")
    print(f"Duration: {format_timestamp(duration)}")
    print(f"Workspaces: {args.workspace_count}")
    print()
    print("Generating wallpapers...")
    print()

    # 4. Generate timestamps
    timestamps = generate_timestamps(duration, args.workspace_count, seed=args.seed)

    # 5. Extract frames
    frames_metadata = []
    workspace_mappings = {}

    for idx, ts in enumerate(timestamps, start=1):
        filename = f"workspace_{idx}.jpg"
        out_file_path = str(output_dir / filename)
        ts_str = format_timestamp(ts)

        extract_frame(movie_path, ts, out_file_path)

        print(f"Workspace {idx} → {ts_str} → {filename}")

        workspace_mappings[str(idx)] = out_file_path
        frames_metadata.append(
            {
                "workspace": idx,
                "timestamp": round(ts, 3),
                "timestamp_formatted": ts_str,
                "file": filename,
                "path": out_file_path,
            }
        )

    # 6. Save metadata.json
    metadata_path = output_dir / "metadata.json"
    metadata_content = {
        "source_movie": movie_path,
        "duration": round(duration, 3),
        "duration_formatted": format_timestamp(duration),
        "workspace_count": args.workspace_count,
        "frames": frames_metadata,
    }

    try:
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata_content, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save metadata file: {e}")

    # 7. Update config/config.toml
    config_path = str(project_root / "config" / "config.toml")
    update_config_toml(config_path, workspace_mappings)

    print()
    print(f"✓ Generated {args.workspace_count} wallpapers")
    print(f"✓ Saved to {output_dir}")
    print(f"✓ Updated config/config.toml")


if __name__ == "__main__":
    main()
