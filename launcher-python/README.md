# Oke Launcher (Python)

A zero-dependency, TV-style dashboard launcher for Windows (also runs on macOS/Linux) built with Python's standard library only. Open a prebuilt EXE or run `launch.py` and you get a big-screen grid of your apps, streaming sites, files and system tools — a "living-room menu" for your PC.

![type: no third-party dependencies](https://img.shields.io/badge/stdlib%20only-no%20pip%20installs-brightgreen)

## Quick start

- **EXE (Windows, easiest):** download `Okelauncher-windows-exe` from the repo's GitHub Actions artifacts, unzip, and double-click `Okelauncher.exe`. A starter `launchers.json` is created next to the EXE on first run.
- **From source:** `python launch.py` (text menu) or `python launch.py --gui` (dashboard). On a normal Python install no extra packages are needed.

First run creates a starter config with a few example tiles (Netflix, Spotify, YouTube …) so the dashboard is never empty.

## The dashboard

`Okelauncher.exe` / `launch.py --gui` opens a dark entertainment-centre dashboard:

- **Left navigation rail** — Home, All apps, Favourites, System monitor, plus all 20 category pages.
- **Category tiles (home page)** — My Computer, Movies & TV, Videos, Music & Audio, Internet & Browser, Gaming, Photos & Gallery, Files & Storage, Live TV & Streaming, Applications (shows everything), Downloads, Cloud & Network, PC Settings (system info), Tools & Utilities, Radio & Podcasts, Calendar & Clock, Productivity, Security & Privacy, Connected Devices, Power & Exit.
- **Top bar** — brand, search box, live clock, date and local weather.
- **Recently played strip** on Home — your last launches, stored in `launcher_history.json` beside the config.
- **System monitor** page — OS, CPU, load, RAM and per-disk free space (no extra packages).
- **Power & Exit** page — Sleep / Restart / Shut down (with a confirm dialog) and Close launcher.
- **Keyboard**: arrows move between tiles, Enter opens, double-click works, `F11` toggles full-screen, `Tab` jumps to the nav rail, `Escape` closes. Click any tile to launch.
- **Buttons (bottom right)** — ＋ Add app, ★ Favorite, ✕ Remove, ⛶ Fullscreen, Close.
- **Search** — typing anywhere jumps to the search box and filters live.

Entries land in a category page when one of their `tags` matches the category's tags.

## Weather (automatic)

The top-right weather chip needs **no configuration**: the launcher detects your approximate location by IP, then fetches the current temperature from open-meteo. Units are °F for US locations, °C elsewhere. To opt out put `"weather": false` in `launchers.json`, or pin a location with `"weather": {"lat": 48.85, "lon": 2.35}` (add `"unit": "celsius"` if you like).

## Launchers.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "theme": "midnight",
  "entries": [
    {
      "name": "Doctor",
      "type": "shell",
      "command": "echo launcher works",
      "icon": "D",
      "color": "#2d8a54",
      "tags": ["tools", "diagnostics"],
      "favorite": true
    },
    {
      "name": "Netflix",
      "type": "url",
      "command": "https://www.netflix.com",
      "icon": "N",
      "color": "#e50914",
      "tags": ["movies", "tv", "streaming"]
    }
  ]
}
```

Fields per entry:

| Field | Meaning |
| --- | --- |
| `name` | Tile label |
| `type` | `shell` (run as command) or `url` (open in browser) — auto-detected |
| `command` | The command line or URL |
| `cwd` | Optional working directory for shell entries |
| `tags` | Dashboards category membership (e.g. `["movies", "streaming"]`) |
| `favorite` | Pinned to the Favourites page |
| `icon` | Tile glyph — a letter, symbol or emoji |
| `color` | Tile background as `#rrggbb` |

### Themes

Set `"theme"` in `launchers.json`:

- `"midnight"` — deep blue-black (default)
- `"oled"` — pure black, multicolour accent (great for TV panels)
- `"sapphire"` — navy blue

## CLI

```
launch.py                 interactive fullscreen-ish text menu (fallback)
launch.py --gui           open the dashboard
launch.py --list          print all entries
launch.py netflix         run the first entry matching a name
launch.py --add           add an entry in the terminal
launch.py --remove NAME   remove an entry
launch.py --config PATH   use a custom config file
```

By default the config lives beside the script (next to the EXE when frozen), falling back to `~/.config/universal-launcher/launchers.json`.

## Building the EXE locally

```
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name Okelauncher launch.py
pyinstaller --noconfirm --onefile --console --name Okelauncher-cli launch.py
```

Or let GitHub Actions do it: push to this branch and download the `Okelauncher-windows-exe` artifact from the workflow run. (Artifacts expire after 90 days.)

## Current dashboard scope vs. ideas inbox

Included: 20 categories, left navigation, recently played, favourites, quick launch, live search, weather chip, system monitor/storage read-out, themes, full-screen/windowed toggle, add/favorite/remove management, sleep/restart/shutdown.

Not implemented yet (possible future work): resume-watching positions, screen mirroring/casting, phone remote control, voice commands, automatic media-library scanning, multiple user profiles, screensaver mode, custom background images, GPU statistics, animated transitions.
