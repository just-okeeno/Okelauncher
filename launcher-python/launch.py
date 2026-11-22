#!/usr/bin/env python3
"""Universal launcher: one menu for apps, shell commands, scripts, and URLs.

Zero third-party dependencies. Works wherever Python 3.9+ runs.

Usage:
    launch.py                 interactive picker (search, arrows, Enter to run)
    launch.py <name>          run the first entry matching <name> and exit
    launch.py --list          list all entries
    launch.py --add           add a new entry
    launch.py --remove NAME   remove an entry
    launch.py --config FILE   use FILE instead of the default config
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

try:
    import termios
    import tty

    POSIX = True
except ImportError:
    POSIX = False

RESET, DIM, BOLD, CYAN = "\033[0m", "\033[2m", "\033[1m", "\033[36m"


def script_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_config_path() -> Path:
    env = os.environ.get("UL_CONFIG")
    if env:
        return Path(env).expanduser()
    local = script_base() / "launchers.json"
    if local.is_file():
        return local
    return Path.home() / ".config" / "universal-launcher" / "launchers.json"


def seed_config(path: Path) -> None:
    starter = {
        "entries": [
            {"name": "Doctor", "type": "shell", "command": "echo launcher works", "tags": ["diagnostics"], "favorite": True},
            {"name": "GitHub", "type": "url", "command": "https://github.com"},
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(starter, indent=2) + "\n", encoding="utf-8")
    print(f"created starter config at {path}")


def load_config(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"error: cannot read config {path}: {exc}")
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        sys.exit(f"error: config {path} must contain an 'entries' list")
    return entries


def save_config(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"$schema": "universal-launcher/v1", "entries": entries}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def normalize(entry: dict, index: int) -> dict:
    if not isinstance(entry, dict):
        raise ValueError(f"entries[{index}] must be an object, got {type(entry).__name__}")
    name = str(entry.get("name") or entry.get("command") or f"entry-{index + 1}")
    etype = str(entry.get("type", "")).lower()
    if etype not in ("shell", "url"):
        etype = "url" if str(entry.get("command", "")).startswith(("http://", "https://")) else "shell"
    return {
        "name": name,
        "type": etype,
        "command": str(entry.get("command", "")),
        "cwd": entry.get("cwd") or None,
        "tags": [str(t) for t in entry.get("tags", [])],
        "favorite": bool(entry.get("favorite", False)),
    }


def run_entry(entry: dict) -> int:
    command, etype, cwd = entry["command"], entry["type"], entry["cwd"]
    if not command:
        print("error: entry has no command")
        return 1
    print(f"▶ {entry['name']}: {command}")
    if etype == "url":
        webbrowser.open(command)
        return 0
    expanded_cwd = Path(cwd).expanduser() if cwd else None
    if expanded_cwd and not expanded_cwd.is_dir():
        print(f"error: cwd does not exist: {expanded_cwd}")
        return 1
    try:
        return subprocess.call(command, shell=True, cwd=expanded_cwd)
    except OSError as exc:
        print(f"error: {exc}")
        return 1


def fuzzy_score(needle: str, haystack: str) -> int:
    if not needle:
        return 1
    needle, haystack = needle.lower(), haystack.lower()
    if needle in haystack:
        return 100 - haystack.index(needle)
    score, pos = 0, 0
    for char in needle:
        pos = haystack.find(char, pos)
        if pos < 0:
            return -1
        score += 1
        pos += 1
    return score


def visible_entries(entries: list[dict], query: str) -> list[dict]:
    scored = []
    for entry in entries:
        hay = " ".join([entry["name"], entry["command"], " ".join(entry["tags"])])
        name_score = fuzzy_score(query, entry["name"])
        if name_score > 0:
            name_score += 5
        score = max(name_score, fuzzy_score(query, hay))
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], not pair[1]["favorite"], pair[1]["name"].lower()))
    return [entry for _, entry in scored]


def render(matches: list[dict], query: str, selected: int) -> None:
    print("\033[2J\033[H", end="")
    print(f"{BOLD}Universal launcher{RESET}  {DIM}type to search · ↑↓ select · Enter run · f favorite · q quit{RESET}\n")
    if not matches:
        print(f"{DIM}  no matches for {query!r}{RESET}")
    for i, entry in enumerate(matches):
        marker = "★" if entry["favorite"] else " "
        kind = "url" if entry["type"] == "url" else "sh"
        line = f" {marker} {entry['name']}  {DIM}[{kind}] {entry['command']}{RESET}"
        prefix = f"{CYAN}{BOLD}▸{RESET}" if i == selected else " "
        print(f"{prefix}{line}")
    sys.stdout.flush()


def read_key() -> str:
    if not POSIX:
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch(), "other")
        return {"\r": "enter", "\x1b": "esc", "\x08": "backspace", "\x03": "quit"}.get(ch, ch)
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            if not sys.stdin.read(1):
                return "esc"
            code = sys.stdin.read(1)
            return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(code, "other")
        return {"\r": "enter", "\n": "enter", "\x7f": "backspace", "\x03": "quit", "\x04": "quit"}.get(ch, ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def interactive(entries: list[dict], path: Path) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return fallback_picker(entries)
    query, selected = "", 0
    while True:
        matches = visible_entries(entries, query)
        selected = min(selected, max(len(matches) - 1, 0))
        render(matches, query, selected)
        key = read_key()
        if key == "quit" or key == "q" or key == "esc":
            print("\033[2J\033[H", end="")
            return 0
        if key == "backspace":
            query, selected = query[:-1], 0
        elif key == "up":
            selected = max(selected - 1, 0)
        elif key == "down":
            selected = min(selected + 1, max(len(matches) - 1, 0))
        elif key == "enter":
            if not matches:
                continue
            print("\033[2J\033[H", end="")
            code = run_entry(matches[selected])
            print(f"\n{DIM}exit code {code} · Enter: back to menu · q: quit{RESET}")
            follow = read_key()
            if follow in ("q", "esc", "quit"):
                print("\033[2J\033[H", end="")
                return code
            query, selected = "", 0
        elif key == "f":
            if matches:
                matches[selected]["favorite"] = not matches[selected]["favorite"]
                save_config(path, entries)
        else:
            query, selected = query + key, 0


def fallback_picker(entries: list[dict]) -> int:
    for i, entry in enumerate(entries):
        kind = "url" if entry["type"] == "url" else "sh"
        print(f"[{i}] {entry['name']}  ({kind}) {entry['command']}")
    try:
        raw = input("run number> ").strip()
    except (EOFError, KeyboardInterrupt):
        return 0
    if raw.isdigit() and int(raw) < len(entries):
        return run_entry(entries[int(raw)])
    return 0


def find_by_name(entries: list[dict], name: str) -> dict | None:
    lowered = name.lower()
    for entry in entries:
        if entry["name"].lower() == lowered:
            return entry
    for entry in entries:
        if lowered in entry["name"].lower():
            return entry
    return None


def cmd_list(entries: list[dict]) -> int:
    if not entries:
        print("no entries; run `launch.py --add` to create one")
        return 0
    width = max(len(e["name"]) for e in entries)
    for entry in entries:
        star = "★" if entry["favorite"] else " "
        kind = "url" if entry["type"] == "url" else "sh"
        tags = f" [{','.join(entry['tags'])}]" if entry["tags"] else ""
        line = f"{star} {entry['name']:<{width}}  {kind:<4}{tags} {entry['command']}"
        if entry["cwd"]:
            line += f"  (cwd: {entry['cwd']})"
        print(line)
    return 0


def cmd_add(entries: list[dict], path: Path) -> int:
    name = input("name: ").strip()
    command = input("command or URL: ").strip()
    if not command:
        sys.exit("error: a command or URL is required")
    etype = input("type [shell/url] (enter = auto): ").strip().lower()
    cwd = input("working directory (enter = inherit): ").strip() or None
    tags = [t.strip() for t in input("tags, comma-separated (enter = none): ").split(",") if t.strip()]
    entry = normalize({"name": name, "command": command, "type": etype, "cwd": cwd, "tags": tags}, len(entries))
    entries.append(entry)
    save_config(path, entries)
    print(f"saved {entry['name']} to {path}")
    return 0


def cmd_remove(entries: list[dict], path: Path, name: str) -> int:
    entry = find_by_name(entries, name)
    if not entry:
        sys.exit(f"error: no entry matches {name!r}")
    entries.remove(entry)
    save_config(path, entries)
    print(f"removed {entry['name']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Universal launcher: apps, commands, scripts, URLs")
    parser.add_argument("name", nargs="?", help="run the first entry matching this name")
    parser.add_argument("--config", type=Path, default=None, help="config file (default: launchers.json beside script, else ~/.config/universal-launcher/launchers.json)")
    parser.add_argument("--list", action="store_true", help="list entries")
    parser.add_argument("--add", action="store_true", help="add an entry interactively")
    parser.add_argument("--remove", metavar="NAME", help="remove an entry")
    args = parser.parse_args()

    path = args.config or default_config_path()
    if not path.is_file():
        seed_config(path)
    try:
        entries = [normalize(e, i) for i, e in enumerate(load_config(path))]
    except ValueError as exc:
        sys.exit(f"error: invalid config {path}: {exc}")

    if args.remove:
        return cmd_remove(entries, path, args.remove)
    if args.add:
        return cmd_add(entries, path)
    if args.list:
        return cmd_list(entries)
    if args.name:
        entry = find_by_name(entries, args.name)
        if not entry:
            sys.exit(f"error: no entry matches {args.name!r}")
        return run_entry(entry)
    return interactive(entries, path)


if __name__ == "__main__":
    sys.exit(main())
