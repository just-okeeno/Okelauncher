# Oke OS (Python)

Oke OS is a zero-dependency, "next-gen console OS" shell for Windows (also runs on macOS/Linux) built with Python's standard library only. Open a prebuilt EXE or run `launch.py` and it serves a frosted-glass TV dashboard on your own machine (`127.0.0.1` only) and opens it in your browser — with a boot splash, a multi-user PIN lock screen, an app store and a photo/video library, it turns any PC into a console-style appliance.

![type: no third-party dependencies](https://img.shields.io/badge/stdlib%20only-no%20pip%20installs-brightgreen)

## Quick start

- **EXE (Windows, easiest):** download `Okelauncher-windows-exe` from the repo's GitHub Actions artifacts, unzip, and double-click `Okelauncher.exe`. Your default browser opens the dashboard; a starter `launchers.json` is created next to the EXE on first run.
- **From source:** `python launch.py` (terminal menu) or `python launch.py --gui` (browser dashboard). The server binds to `127.0.0.1` on a random port — it never accepts traffic from the network.

First run creates a starter config with a few example tiles (Netflix, Spotify, YouTube …) so the dashboard is never empty.

## The dashboard (Next-Gen TV & Console UI)

- **OS experience** — animated **boot splash** ("Mounting launchers.json… → Welcome to Oke OS") and a full-screen **lock screen** with **user profiles + PIN** (giant clock, date, weather, profile chips and a PIN keypad; header 🔒 button or Power page > Lock).
- **Frosted glass surfaces + ambient glow orbs** that shift colour per category.
- **Top status bar** — brand, live CPU / RAM / Disk telemetry pills, zero-config weather chip, sound toggle, search (press `/`), themes drawer, and live clock + date.
- **Left floating nav rail** with a spring-animated active pill: Home, All apps, Favourites, System monitor, Photos & Videos, Oke Store, all 20 categories, and Power & Exit.
- **User profiles with PIN** — sign in as different users on the lock screen. PINs are stored salted+hashed (SHA-256, never in plain text); profiles without a PIN unlock instantly. Each profile keeps its own recently-played history.
- **Photos & Videos (media library)** — Oke OS scans your Pictures, Videos, Downloads, Desktop, Music and OneDrive folders for pictures and videos and organises them by folder. Browse folder cards, then view photos in a lightbox, play MP4/WebM/MOV files in an in-page video player, or open exotic formats in your system player. Rescan button included (newest 4000 files, depth 5).
- **Oke Store** — a built-in package installer with 16 popular apps & services (Netflix, Spotify, Steam, Discord, VS Code …). "＋ Add to Oke OS" pins the web app to your dashboard instantly; "⬇ Get installer" opens the official download page.
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

### Profiles

Profiles live in the same file under a `profiles` key and are created/edited from the lock screen UI — no editing needed:

```json
"profiles": { "users": { "Owner": {"pin": null}, "Kid": {"pin": "salt$hash"} }, "active": "Owner" }
```

`pin` is always stored as `<salt>$<sha256(salt+pin)>` or `null` (no PIN). History files follow the same pattern: the first profile uses `launcher_history.json`, others get `launcher_history_<name>.json`.

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

Included: 20 categories, glass nav rail with spring pill, recently played (per profile), favourites, quick launch, live search, weather chip, live CPU/RAM/disk telemetry + system monitor page, 4 themes with persistence, 3D tilt + ripples + ambient orbs, launch splash, boot splash, user profiles with PIN lock screen, Oke Store package installer, automatic PC media scan with photo/video viewer, add/favourite/remove management, sleep/restart/shutdown, terminal fallback menu.

Not implemented yet (possible future work): custom media-scan folders, resume-watching positions, screen mirroring/casting, phone remote control, voice commands, screensaver mode, custom background images, GPU statistics.
