# Oke Launcher (dashboard)

A TV-style dashboard launcher: big clock and date header, automatic live weather, and a grid of colored app tiles you launch with Enter or double-click. Single file, no dependencies beyond Python 3.9+ and `launchers.json`.

## Windows EXE (no Python needed)

Built automatically by the `Build Windows EXE` GitHub Actions workflow: open the [Actions tab](../../actions), pick the latest **Build Windows EXE** run, and download the `Okelauncher-windows-exe` artifact. The zip contains:

- `Okelauncher.exe` — dashboard GUI: double-click to open; search, `↑↓←→` to navigate tiles, `Enter`/double-click to launch, `＋ Add app` / `★ Favorite` / `✕ Remove` buttons manage `launchers.json` from the window itself, `Esc` to close
- `Okelauncher-cli.exe` — terminal version for scripting and keyboard-only use

On first run a starter `launchers.json` is created next to the EXE; edit it to point at your real apps.

## Run from source

```bash
python3 launch.py          # dashboard GUI (same as --gui)
python3 launch.py doctor   # one-shot launch by name
python3 launch.py --list
python3 launch.py --add    # prompts for name, command, icon glyph, tile color
python3 launch.py --remove NAME
python3 launch.py --config /path/to/launchers.json
```

(run `python3 launch.py` with no terminal for the GUI, or in a real terminal you get the keyboard text menu)

## Config

`launchers.json` (created with starter tiles on first run, if missing; side-by-side by default — next to the EXE when frozen — else `~/.config/universal-launcher/launchers.json`; override with `--config` or the `UL_CONFIG` env var):

```json
{
  "entries": [
    { "name": "Netflix", "type": "url", "command": "https://www.netflix.com", "icon": "N", "color": "#e50914" },
    { "name": "VS Code", "type": "shell", "command": "code", "favorite": true },
    { "name": "Backup", "type": "shell", "command": "rsync -a ~/Documents/ /mnt/backup/", "cwd": "/home/you" }
  ]
}
```

- `type`: `shell` (run via the system shell, so pipes and redirects work) or `url` (opens the default browser).
- `cwd`: optional working directory for shell entries.
- `icon`: tile glyph — any letter, symbol, or emoji (defaults to the first letter of the name).
- `color`: tile background as `#rrggbb` (defaults to a neutral dark surface).
- `tags` / `favorite`: optional metadata; tags participate in search and favorites sort first.
- `weather`: optional. Omitted (the default), the dashboard detects your location from your network and shows live weather automatically (°F in the US, °C elsewhere). Set to `false` to turn the chip off, or provide explicit coordinates: `{ "lat": 40.7, "lon": -74.0, "unit": "celsius" }`.

## Notes

- In headless environments, `url` entries follow the platform default browser (on Linux, `$BROWSER`).
- The text menu needs a real terminal (raw tty input on POSIX via `termios`, Windows via `msvcrt`); without one it falls back to a numbered list.
