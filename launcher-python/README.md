# Oke OS (Python)

Oke OS is a zero-dependency, "next-gen console OS" shell for Windows (also runs on macOS/Linux) built with Python's standard library only. Open a prebuilt EXE or run `launch.py` and it serves a frosted-glass TV dashboard on your own machine (`127.0.0.1` only) and opens it in your browser — with a boot splash, lock screen and power controls, it turns any PC into a console-style appliance.

![type: no third-party dependencies](https://img.shields.io/badge/stdlib%20only-no%20pip%20installs-brightgreen)

## Quick start

- **EXE (Windows, easiest):** download `Okelauncher-windows-exe` from the repo's GitHub Actions artifacts, unzip, and double-click `Okelauncher.exe`. Your default browser opens the dashboard; a starter `launchers.json` is created next to the EXE on first run.
- **From source:** `python launch.py` (terminal menu) or `python launch.py --gui` (browser dashboard). The server binds to `127.0.0.1` on a random port — it never accepts traffic from the network.

First run creates a starter config with a few example tiles (Netflix, Spotify, YouTube …) so the dashboard is never empty.

## The dashboard (Next-Gen TV & Console UI)

- **OS experience** — animated **boot splash** ("Mounting launchers.json… → Welcome to Oke OS") and a full-screen **lock screen** (giant clock, date, weather; click or any key to unlock; header 🔒 button or Power page > Lock).
- **Frosted glass surfaces + ambient glow orbs** that shift colour per category.
- **Top status bar** — brand, live CPU / RAM / Disk telemetry pills, zero-config weather chip, sound toggle, search (press `/`), themes drawer, and live clock + date.
- **Left floating nav rail** with a spring-animated active pill: Home, All apps, Favourites, System monitor, all 20 categories, and Power & Exit.
- **Hero banner** that crossfades to the currently focused tile, with a glowing **Launch Now** button.
- **Cards grid** with console focus rings, 3D perspective tilt (toggleable), click ripples and staggered entrance animations.
- **Launch splash** — cinematic progress modal while the real app/command starts.
- **Theme drawer** — Midnight Obsidian, Cyber Aurora, Arctic Frosted Glass, Sunset Amber (persisted to `launchers.json`), plus a 3D-tilt switch.
- **Quick search modal** (`/`) across names, tags and commands.
- **Details modal** — command, type, tags, plus ★ Favourite and 🗑 Remove actions.
- **＋ Add App modal** — name, command/URL, tags, glyph, colour; saved straight to `launchers.json`.
- **Home = "Jump Back In"** — recently played tiles (from `launcher_history.json`) first, then the rest of your library.
- **System Monitor page** — live OS, CPU, RAM and per-disk free space (no extra packages).
- **Power & Exit page** — Sleep / Restart / Shut down with a confirmation modal, and Close launcher.
- **Keyboard / TV navigation** — arrows move focus, Enter launches, `/` search, `A` add, `ESC` closes modals, `F11` full-screens the browser.

Entries land in a category page when one of their `tags` matches the category's tags.

## Weather (automatic)

The weather chip needs **no configuration**: the launcher detects your approximate location by IP, then fetches the current temperature from open-meteo. Units are °F for US locations, °C elsewhere; the chip shows your city. To opt out put `"weather": false` in `launchers.json`, or pin a location with `"weather": {"lat": 48.85, "lon": 2.35}` (add `"unit": "celsius"` if you like). Click the chip to refresh.

## Launchers.json

```json
{
  "$schema": "universal-launcher/v1",
  "theme": "obsidian",
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
| `tags` | Dashboard category membership (e.g. `["movies", "streaming"]`) |
| `favorite` | Pinned to the Favourites page |
| `icon` | Tile glyph — a letter, symbol or emoji |
| `color` | Tile background as `#rrggbb` (used in card gradients) |

### Themes

Set `"theme"` in `launchers.json` or use the in-app Themes drawer: `"obsidian"` (default), `"aurora"`, `"arctic"`, `"sunset"`. Legacy values `midnight`/`oled` map to obsidian and `sapphire` to aurora.

## CLI

```
launch.py                 interactive terminal menu
launch.py --gui           serve the dashboard UI and open it in the browser
launch.py --list          print all entries
launch.py netflix         run the first entry matching a name
launch.py --add           add an entry in the terminal
launch.py --remove NAME   remove an entry
launch.py --config PATH   use a custom config file
```

By default the config lives beside the script (next to the EXE when frozen), falling back to `~/.config/universal-launcher/launchers.json`. Visit the printed `http://127.0.0.1:<port>/` URL if your browser does not open itself; stop the launcher with Ctrl+C or Power & Exit > Close launcher.

## Building the EXE locally

```
pip install pyinstaller
pyinstaller --onefile --windowed --name Okelauncher --add-data "dashboard.html;." launch.py
```

Or let GitHub Actions do it: push to this branch and download the `Okelauncher-windows-exe` artifact from the workflow run. (Artifacts expire after 90 days; ask if you want a permanent GitHub Release instead.)

## Current dashboard scope vs. ideas inbox

Included: 20 categories, glass nav rail with spring pill, recently played, favourites, quick launch, live search, weather chip, live CPU/RAM/disk telemetry + system monitor page, 4 themes with persistence, 3D tilt + ripples + ambient orbs, launch splash, add/favourite/remove management, sleep/restart/shutdown, terminal fallback menu.

Not implemented yet (possible future work): resume-watching positions, screen mirroring/casting, phone remote control, voice commands, automatic media-library scanning, multiple user profiles, screensaver mode, custom background images, GPU statistics.
