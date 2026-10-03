"""
generator.py — Turns movies into workspace wallpapers.

Given a movie file OR a folder of movies and a workspace count:

    1. find the movie file(s)
    2. randomly split the workspace count across the movies
       (how many frames each movie contributes is random)
    3. pick random unique-ish timestamps inside each movie
    4. extract those frames as JPGs with ffmpeg
    5. write metadata.json next to the frames
    6. rewrite the [workspaces] table in config/config.toml
       (paths stored relative to the project root when possible)

Used by main.py (the single documented command) and by
tools/generate_movie_wallpapers.py (a thin standalone CLI kept for
compatibility).
"""

import json
import math
import os
import random
import shutil
import subprocess
from pathlib import Path

from core.config import load_raw_config, save_config


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".m4v", ".mpg", ".mpeg", ".wmv", ".flv", ".ts",
}


def check_dependencies():
    """Verify ffmpeg and ffprobe are installed. Raises RuntimeError."""
    missing = []
    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("ffprobe"):
        missing.append("ffprobe")

    if missing:
        raise RuntimeError(
            f"Required tool(s) missing: {', '.join(missing)}. "
            "Please install FFmpeg (Arch Linux: sudo pacman -S ffmpeg)."
        )


def find_movies(location):
    """
    Return movie file paths from a location.

    location may be a single video file or a folder (scanned non-recursively
    for known video extensions, sorted alphabetically).

    Raises ValueError if the location doesn't exist.
    """
    location = os.path.abspath(location)

    if os.path.isfile(location):
        return [location]

    if not os.path.isdir(location):
        raise ValueError(f"Location does not exist: '{location}'")

    movies = []
    for name in sorted(os.listdir(location)):
        full = os.path.join(location, name)
        if os.path.isfile(full) and os.path.splitext(name)[1].lower() in VIDEO_EXTENSIONS:
            movies.append(full)

    return movies


def split_count_randomly(total, n_movies, rng):
    """
    Randomly split `total` frames across `n_movies`.

    When total >= n_movies, every movie gets at least 1 frame and the
    remainder is distributed uniformly at random (multinomial).
    When total < n_movies, `total` distinct movies are chosen at random,
    one frame each.

    Returns a list of length n_movies summing to exactly `total`.
    """
    if n_movies <= 0 or total <= 0:
        return []

    if total < n_movies:
        picks = set(rng.sample(range(n_movies), total))
        return [1 if i in picks else 0 for i in range(n_movies)]

    shares = [1] * n_movies
    for _ in range(total - n_movies):
        shares[rng.randrange(n_movies)] += 1
    return shares


def format_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS format."""
    total_seconds = int(math.floor(max(0.0, seconds)))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_video_duration(movie_path: str) -> float:
    """Extract video duration in seconds using ffprobe. Raises RuntimeError."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        movie_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise RuntimeError("ffprobe executable not found.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out while reading '{movie_path}'.")

    if result.returncode != 0:
        detail = result.stderr.strip()
        msg = f"ffprobe failed to read video file: '{movie_path}'"
        raise RuntimeError(f"{msg} ({detail})" if detail else msg)

    output = result.stdout.strip()
    try:
        duration = float(output)
    except ValueError:
        raise RuntimeError(
            f"Could not parse video duration from ffprobe output: '{output}'"
        )

    if duration <= 0:
        raise RuntimeError(f"Video duration is non-positive ({duration}s): '{movie_path}'")

    return duration


def generate_timestamps(duration: float, count: int, rng: random.Random) -> list:
    """Generate unique-ish random timestamps spread across the movie."""
    if count <= 0:
        return []

    # Avoid selecting frames extremely close to the beginning or end of
    # long movies. For short videos, use the full duration range.
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
            f"Notice: frame count ({count}) is high relative to duration "
            f"({duration:.2f}s). Frames will be closely spaced."
        )

    timestamps = []
    for i in range(count):
        t_min = start_sec + i * bucket_width
        t_max = min(start_sec + (i + 1) * bucket_width, end_sec)

        if t_max <= t_min:
            ts = t_min
        else:
            ts = rng.uniform(t_min, t_max)

        timestamps.append(round(ts, 3))

    return timestamps


def extract_frame(movie_path: str, timestamp: float, output_file: str):
    """Extract a single video frame at timestamp using ffmpeg. Raises RuntimeError."""
    cmd = [
        "ffmpeg",
        "-ss", f"{timestamp:.3f}",
        "-i", movie_path,
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        output_file,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg executable not found.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ffmpeg timed out extracting frame at {timestamp:.2f}s from '{movie_path}'."
        )

    if result.returncode != 0 or not os.path.isfile(output_file):
        detail = result.stderr.strip()
        msg = f"ffmpeg failed to extract frame at {timestamp:.2f}s from '{movie_path}'"
        raise RuntimeError(f"{msg} ({detail})" if detail else msg)


def _portable_path(path, project_root):
    """Path relative to project root when under it, absolute otherwise."""
    try:
        rel = os.path.relpath(path, project_root)
    except ValueError:
        return path
    if rel.startswith(".."):
        return path
    return rel


def generate_wallpapers(
    location,
    workspace_count,
    output_dir=None,
    seed=None,
    project_root=None,
    config_path=None,
):
    """
    Full generation pipeline: movies → frames → metadata.json → config.toml.

    Args:
        location: movie file or folder of movies
        workspace_count: total number of workspaces to map
        output_dir: where frames go (default: <project_root>/wallpapers/movie)
        seed: random seed for reproducible splits/timestamps
        project_root: project root (default: parent of this file's dir)
        config_path: config.toml to update (default: <project_root>/config/config.toml)

    Returns:
        (workspaces_dict, metadata_dict)

    Raises:
        ValueError / RuntimeError on fatal input or tool errors.
    """
    if workspace_count <= 0:
        raise ValueError(f"Workspace count must be a positive integer, got {workspace_count}")

    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.abspath(project_root)

    if config_path is None:
        config_path = os.path.join(project_root, "config", "config.toml")

    if output_dir:
        output_dir = Path(output_dir).resolve()
    else:
        output_dir = Path(project_root) / "wallpapers" / "movie"

    # 1. Validate dependencies and inputs
    check_dependencies()

    location_abs = os.path.abspath(location)
    if os.path.isfile(location_abs):
        print(f"Movie: {location_abs}")
    else:
        print(f"Scanning folder: {location_abs}")

    movies = find_movies(location_abs)
    if not movies:
        raise ValueError(
            f"No video files found in '{location_abs}' "
            f"(looked for: {', '.join(sorted(VIDEO_EXTENSIONS))})"
        )
    print(f"Found {len(movies)} movie(s)")

    # 2. Randomly distribute the workspace count across the movies
    rng = random.Random(seed)
    splits = split_count_randomly(workspace_count, len(movies), rng)

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Failed to create output directory '{output_dir}': {e}")

    # 3. Extract frames movie by movie
    mappings = {}
    frames_metadata = []
    used_movies = []

    for movie, count_for_movie in zip(movies, splits):
        if count_for_movie <= 0:
            continue

        try:
            duration = get_video_duration(movie)
        except RuntimeError as e:
            # One unreadable movie must not kill the whole run
            print(f"Warning: skipping '{movie}': {e}")
            continue

        used_movies.append(movie)
        print(f"  {os.path.basename(movie)} — {format_timestamp(duration)} → {count_for_movie} frame(s)")

        for ts in generate_timestamps(duration, count_for_movie, rng):
            idx = len(mappings) + 1
            filename = f"workspace_{idx}.jpg"
            out_file_path = str(output_dir / filename)

            try:
                extract_frame(movie, ts, out_file_path)
            except RuntimeError as e:
                # A single bad frame must not kill the whole run
                print(f"Warning: {e} — skipping this frame")
                continue

            ts_str = format_timestamp(ts)
            print(f"    Workspace {idx} → {ts_str} → {filename}")

            stored_path = _portable_path(out_file_path, project_root)
            mappings[str(idx)] = stored_path
            frames_metadata.append(
                {
                    "workspace": idx,
                    "timestamp": round(ts, 3),
                    "timestamp_formatted": ts_str,
                    "file": filename,
                    "path": stored_path,
                    "movie": movie,
                }
            )

    if not mappings:
        raise RuntimeError("No frames could be extracted from any movie.")

    # 4. Save metadata.json
    metadata_content = {
        "source_location": location_abs,
        "movies": used_movies,
        "workspace_count": len(mappings),
        "frames": frames_metadata,
    }

    try:
        with open(output_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata_content, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save metadata file: {e}")

    # 5. Update config/config.toml ([workspaces] replaced, everything else kept)
    existing_config = load_raw_config(config_path)
    existing_config["workspaces"] = mappings
    save_config(config_path, existing_config)

    print()
    print(f"✓ Generated {len(mappings)} wallpapers → {output_dir}")
    print(f"✓ Updated {config_path}")

    return mappings, metadata_content
