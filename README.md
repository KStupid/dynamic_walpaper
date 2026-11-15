# Dynamic Workspace Wallpaper

A small, **stdlib-only** Python daemon for **Hyprland** (Linux Wayland compositor).
It watches which virtual workspace you switch to and instantly changes your
desktop wallpaper to match — so each workspace gets its own wallpaper (and, if
you use the generator, the wallpaper becomes a "memory" from a movie you've seen).

## The one documented command

```bash
python main.py <location> <no_of_workspace>
```

* `<location>` — a **movie file**, a **folder of movies**, a **folder of images**, or a **single image/file** (scanned recursively)
* `<no_of_workspace>` — how many wallpapers to generate across all media

That's it. Everything else happens automatically:

1. **Recursively scans** `<location>` for all video and image files in all subfolders
2. **Filters by media type** (default: mixed; use `--media-type movies` or `--media-type photos`)
3. **Randomly splits** the screenshot count per movie/image
4. **For single media** (only 1 movie/photo found): assigns that same item to ALL workspaces
5. **Extracts random frames as JPGs** into `wallpapers/` (videos only; images used directly)
6. **Rewrites `config/config.toml`** with the new paths
7. **Starts the background listener** (wallpaper daemon) — no further action needed

After that, just switch workspaces (`Super+1` … `Super+10`) and the wallpaper
swaps to match. Normal behavior: workspace switch → matching wallpaper.
```

## Optional flags

```bash
python main.py ~/Movies 10                    # mixed mode (default)
python main.py ~/Movies 10 --media-type movies # only video files (recursive)
python main.py ~/Pictures 10 --media-type photos  # only image files (recursive)
python main.py movie.mp4 6                     # single movie, 6 workspaces
```

### `--media-type`

Choose what type of media to scan for:

* **`mixed`** (default): both videos and images — videos get frames extracted, images used directly
* **`movies`**: only video files (MP4, MKV, AVI, etc.) — recursive folder scanning
* **`photos`**: only image files (JPG, PNG, WebP, GIF, BMP) — recursive folder scanning

## How the two parts fit together

```
python main.py ~/Movies 10
  │
  ├─► tools/generate_movie_wallpapers.py  (hardly more than a thin wrapper now)
  │     folder scan → random per-movie split → ffmpeg frame extraction
  │     → wallpapers/workspace_N.jpg
  │     → wallpapers/metadata.json
  │     → config/config.toml rewritten
  │
  └─► main.py  (the runtime daemon)
        load config → build mapping → WallpaperManager(monitor) → listen()
          │
          ▼
        Hyprland IPC socket → "workspacev2>><id>,<id>" events
          │
          ▼
        mapping.get(id) → <wallpaper>.jpg → hyprctl hyprpaper wallpaper
```

## Requirements

* **Python 3.11+** (stdlib only — `tomllib`, `int | None` syntax; no `pip install` needed)
* **ffmpeg / ffprobe** — only if you run the generator tool
* A running **Hyprland** session with **hyprpaper** — for the daemon (the `hyprctl`
  IPC socket, usually at `$XDG_RUNTIME_DIR/hypr/<instance_sig>/.socket2.sock`)

## Usage

### Generate wallpapers from a movie (or a whole folder)

```bash
python main.py ~/Movies 10
# or, a single movie file:
python main.py /path/to/clip.mp4 6
```

Optional flags:

```bash
python main.py ~/Movies 10 --output-dir ~/wallpapers --seed 42
python main.py ~/Movies 10 --media-type movies --seed 42
python main.py ~/Pictures 10 --media-type photos --seed 42
```

### Run the listener only (after generation)

```bash
python main.py --listen
```

Or just `python main.py` (launchs as a background daemon, `--listen` is the default).

### At boot

Add to `~/.config/hypr/hyprland.conf`:

```ini
exec-once = python /path/to/dynamic-wallpaper/main.py /home/you/Movies 10
```

## Files at a glance

| Path | Purpose |
|---|---|
| `main.py` | Runtime daemon entrypoint: generation + config + background listener |
| `core/config.py` | Config loading/parsing; portable relative paths; `monitor` key (`"auto"` → auto-detect via `hyprctl monitors`) |
| `core/generator.py` | **New.** Folder scanning, random per-movie split, shared ffmpeg pipeline, metadata + config writers |
| `core/wallpaper.py` | WallpaperManager — correct hyprpaper protocol (`listloaded` → `preload` → `wallpaper`), monitor detection, failure reporting |
| `platforms/hyprland.py` | Hyprland IPC client: event loop, bytes-safe buffering, decode-safe parsing, failure surfacing |
| `tools/generate_movie_wallpapers.py` | Thin CLI wrapper around `core.generator` (kept for compatibility) |
| `config/config.toml` | Workspace → wallpaper mapping; portable relative paths; `monitor` key |
| `doc/project_overview.txt` | Full internal walkthrough: every file's input/output, flow, limitations, plan |

## Limitations

* The doc's "future" items (periodic re-generation of screenshots, auto-detecting
  the workspace count, user-configurable randomness, automated movie-to-workspace
  assignment) are **not** implemented — see `doc/project_overview.txt`.
* The daemon connects to your *current* Hyprland instance. If the compositor is
  restarted, the IPC socket changes and the daemon won't reconnect (see
  `doc/project_overview.txt` §4 for the hardening options).

## Development

Stdlib-only. To verify after a change:

```bash
python3 -m compileall core platforms tools main.py
python3 -m unittest tests.test_generator   # if you add the test suite
python main.py /tmp/fake_movies 4          # live smoke test in a copy
```
