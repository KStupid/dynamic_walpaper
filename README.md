# Dynamic Workspace Wallpaper

A small, **stdlib-only** Python daemon for **Hyprland** (Linux Wayland compositor).
It watches which virtual workspace you switch to and instantly changes your
desktop wallpaper to match — so each workspace gets its own wallpaper (and, if
you use the generator, the wallpaper becomes a "memory" from a movie you've seen).

## The one documented command

```bash
python main.py <location> <no_of_workspace>
```

* `<location>` — a **movie file**, or a **folder of movies** (scanned automatically)
* `<no_of_workspace>` — how many wallpapers to generate across all movies

That's it. Everything else happens automatically:

1. Scans `<location>` for movies (or uses the single file you gave)
2. Splits the screenshot count **randomly** per movie
3. Extracts random frames as JPGs into `wallpapers/`
4. Rewrites `config/config.toml` with the new paths
5. Starts the background listener (wallpaper daemon) — no further action needed

After that, just switch workspaces (`Super+1` … `Super+10`) and the wallpaper
swaps to match. Normal behavior: workspace switch → matching wallpaper.

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
