# Universal launcher

One searchable menu for everything you start: apps, shell commands, scripts, and URLs. Single file, no dependencies beyond Python 3.9+ and `launchers.json` next to `launch.py`.

A standalone Windows `Okelauncher.exe` (no Python needed) is built automatically by the `Build Windows EXE` GitHub Actions workflow: open the [Actions tab](../../actions), pick the latest run, and download the `Okelauncher-windows-exe` artifact. Keep it (plus its `launchers.json`, created on first run) in a folder on your `PATH`.

## Run

```bash
python3 launch.py
```

In the picker: type to fuzzy-filter, `↑`/`↓` to select, `Enter` to run, `f` to toggle favorite (persisted), `q` to quit. Favorites float to the top and are marked `★`. If stdin or stdout is not a TTY (for example a piped run), it falls back to a numbered list.

## Direct run

```bash
python3 launch.py doctor   # exact or substring name match; runs and exits
python3 launch.py --list
python3 launch.py --add
python3 launch.py --remove NAME
python3 launch.py --config /path/to/launchers.json
```

Tip: drop a short alias in your shell profile, e.g. `alias go='python3 /path/to/launch.py'` (or a `go.bat` wrapping the EXE), then `go` for the menu or `go github` for a one-shot launch.

## Config

`launchers.json` (created with starter entries on first run, if missing; side-by-side by default — next to the EXE when frozen — else `~/.config/universal-launcher/launchers.json`; override with `--config` or the `UL_CONFIG` env var):

```json
{
  "entries": [
    { "name": "VS Code", "type": "shell", "command": "code", "favorite": true },
    { "name": "Docs", "type": "url", "command": "https://docs.example.com" },
    { "name": "Backup home", "type": "shell", "command": "rsync -a ~/Documents/ /mnt/backup/", "cwd": "/home/you" }
  ]
}
```

- `type`: `shell` (run via the system shell, so pipes and redirects work) or `url` (opens the default browser).
- `cwd`: optional working directory for shell entries.
- `tags` / `favorite`: optional metadata; tags participate in fuzzy search.

## Notes

- In headless environments, `url` entries follow the platform default browser (on Linux, `$BROWSER`).
- The interactive picker needs a real terminal; it uses raw tty input on POSIX (`termios`) and Windows (`msvcrt`), with a plain numbered-list fallback otherwise.
