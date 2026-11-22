#!/usr/bin/env python3
"""Universal launcher: one menu for apps, shell commands, scripts, and URLs.

Zero third-party dependencies. Works wherever Python 3.9+ runs.

Usage:
    launch.py                 interactive picker (search, arrows, Enter to run)
    launch.py --gui           dashboard window with clock, weather, and app tiles
                              (default when run as a windowed EXE)
    launch.py <name>          run the first entry matching <name> and exit
    launch.py --list          list all entries
    launch.py --add           add a new entry
    launch.py --remove NAME   remove an entry
    launch.py --config FILE   use FILE instead of the default config
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import threading
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
            {"name": "Doctor", "type": "shell", "command": "echo launcher works", "icon": "D", "color": "#2d8a54", "tags": ["diagnostics"], "favorite": True},
            {"name": "Netflix", "type": "url", "command": "https://www.netflix.com", "icon": "N", "color": "#e50914"},
            {"name": "YouTube", "type": "url", "command": "https://www.youtube.com", "icon": "▶", "color": "#ff0000"},
            {"name": "Prime Video", "type": "url", "command": "https://www.primevideo.com", "icon": "P", "color": "#00a8e1"},
            {"name": "Spotify", "type": "url", "command": "https://open.spotify.com", "icon": "♫", "color": "#1db954"},
            {"name": "Twitch", "type": "url", "command": "https://www.twitch.tv", "icon": "T", "color": "#9146ff"},
            {"name": "GitHub", "type": "url", "command": "https://github.com", "icon": "G", "color": "#24292e"},
            {"name": "Local file server", "type": "shell", "command": "python -m http.server 8642 --bind 127.0.0.1", "icon": "▤", "color": "#5e81ac"},
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(starter, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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


def load_weather_config(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    weather = data.get("weather") if isinstance(data, dict) else None
    if isinstance(weather, dict) and "lat" in weather and "lon" in weather:
        return weather
    return None


def save_config(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"$schema": "universal-launcher/v1", "entries": entries}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
        "icon": str(entry.get("icon") or ""),
        "color": str(entry.get("color") or ""),
    }


def force_utf8_output() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


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


WEATHER_CODES = {
    0: ("Clear", "☀"),
    1: ("Mostly clear", "🌤"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁"),
    45: ("Fog", "🌫"),
    48: ("Fog", "🌫"),
    51: ("Light drizzle", "🌦"),
    53: ("Drizzle", "🌦"),
    55: ("Heavy drizzle", "🌧"),
    61: ("Light rain", "🌦"),
    63: ("Rain", "🌧"),
    65: ("Heavy rain", "🌧"),
    71: ("Light snow", "🌨"),
    73: ("Snow", "🌨"),
    75: ("Heavy snow", "❄"),
    80: ("Light showers", "🌦"),
    81: ("Showers", "🌧"),
    82: ("Heavy showers", "🌧"),
    85: ("Snow showers", "🌨"),
    86: ("Snow showers", "❄"),
    95: ("Thunderstorm", "⛈"),
    96: ("Thunderstorm", "⛈"),
    99: ("Hail storm", "⛈"),
}


def weather_summary(temp: float, code: int, unit: str = "fahrenheit") -> str:
    description, glyph = WEATHER_CODES.get(int(code), ("Weather", "🌡"))
    if unit.lower().startswith("f"):
        value = f"{round(temp)}°F"
    else:
        value = f"{round(temp)}°C"
    return f"{value} {glyph} {description}"


def fetch_weather_async(root, label, config: dict) -> None:
    import urllib.request

    lat, lon = config["lat"], config["lon"]
    unit = str(config.get("unit", "fahrenheit"))
    params = f"latitude={lat}&longitude={lon}&current=temperature_2m,weather_code"
    params += f"&temperature_unit={'fahrenheit' if unit.lower().startswith('f') else 'celsius'}"
    url = f"https://api.open-meteo.com/v1/forecast?{params}"

    def work():
        try:
            with urllib.request.urlopen(url, timeout=6) as resp:
                data = json.load(resp)
            current = data.get("current", {})
            text = weather_summary(current["temperature_2m"], current.get("weather_code", 0), unit)
            root.after(0, lambda: label.config(text=text))
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()


def launch_gui(entries: list[dict], path: Path, weather_config: dict | None = None) -> int:
    try:
        import tkinter as tk
        from tkinter import font as tkfont
    except ImportError:
        print("tkinter is not available in this Python build; using the text menu instead")
        return interactive(entries, path)

    BG, FG, DIM, MUTED = "#0f1115", "#e8eaed", "#9aa0a6", "#5f6368"
    SURFACE, SURFACE_HI, ACCENT = "#1b1e26", "#262b36", "#89b4fa"

    root = tk.Tk()
    root.title("Oke Launcher")
    root.configure(bg=BG)
    root.geometry("1180x720")
    root.minsize(940, 560)

    family = tkfont.nametofont("TkDefaultFont").actual("family")
    COLS, TILE_W, TILE_H = 6, 150, 118

    state = {"tiles": [], "index": 0, "matches": list(entries)}

    header = tk.Frame(root, bg=BG)
    clock_label = tk.Label(header, text="", bg=BG, fg=FG, font=(family, 40, "bold"))
    date_label = tk.Label(header, text="", bg=BG, fg=DIM, font=(family, 13))
    weather_label = tk.Label(header, text="", bg=BG, fg=DIM, font=(family, 13))

    clock_sub = tk.Frame(header, bg=BG)
    clock_label.pack(in_=clock_sub, side="left", anchor="w")
    date_label.pack(in_=clock_sub, side="left", anchor="s", padx=(16, 0), ipady=6)

    search_container = tk.Frame(root, bg=BG)
    search_var = tk.StringVar()
    search = tk.Entry(
        search_container,
        textvariable=search_var,
        bg=SURFACE,
        fg=FG,
        insertbackground=FG,
        relief="flat",
        font=(family, 13),
    )
    search_hint = tk.Label(search_container, text="Search by name, command, or tag · Enter runs · Esc closes", bg=BG, fg=MUTED, font=(family, 10))

    canvas = tk.Canvas(root, bg=BG, bd=0, highlightthickness=0)
    inner = tk.Frame(canvas, bg=BG)
    scrollbar = tk.Scrollbar(root, command=canvas.yview, bg=BG, troughcolor=BG, bd=0)
    inner_window = canvas.create_window((0, 0), window=inner, anchor="nw")

    status = tk.Label(root, text="", bg=BG, fg=DIM, anchor="w", font=(family, 11))

    header.pack(fill="x", padx=28, pady=(22, 4))
    clock_sub.pack(side="left")
    weather_label.pack(side="right")

    search_container.pack(fill="x", padx=28, pady=(8, 10))
    search.pack(fill="x", ipady=9)
    search_hint.pack(anchor="w", pady=(6, 0))
    scrollbar.pack(side="right", fill="y", padx=(0, 2))
    canvas.pack(fill="both", expand=True, padx=28)
    status.pack(fill="x", padx=28, pady=(8, 14))

    def tick():
        now = datetime.datetime.now()
        clock_label.config(text=now.strftime("%H:%M"))
        date_label.config(text=now.strftime("%A, %B ") + str(now.day))
        root.after(20000, tick)

    def refresh(*_):
        query = search_var.get().strip()
        state["matches"] = visible_entries(entries, query)
        state["index"] = min(state["index"], max(len(state["matches"]) - 1, 0))
        build_tiles()
        if not state["matches"]:
            status.config(text="no matches" if query else "add entries via launchers.json or `Okelauncher-cli --add`")
        else:
            status.config(text="")

    def build_tiles():
        for child in inner.winfo_children():
            child.destroy()
        state["tiles"] = []
        for i, entry in enumerate(state["matches"]):
            color = entry["color"] or SURFACE
            tile = tk.Frame(
                inner,
                bg=color,
                width=TILE_W,
                height=TILE_H,
                highlightthickness=3,
                highlightbackground=BG,
                highlightcolor=ACCENT,
            )
            tile.pack_propagate(False)
            glyph = entry["icon"] or entry["name"][:1].upper()
            icon_label = tk.Label(tile, text=glyph, bg=color, fg="#ffffff", font=(family, 30, "bold"))
            name_label = tk.Label(tile, text=entry["name"], bg=color, fg="#ffffff", font=(family, 11), wraplength=TILE_W - 20)
            icon_label.pack(expand=True)
            name_label.pack(padx=8, pady=(0, 10))
            tile.grid(row=i // COLS, column=i % COLS, padx=9, pady=9)
            tile.bind("<Enter>", lambda _e, idx=i: select(idx))
            tile.bind("<Button-1>", lambda _e, idx=i: select(idx))
            tile.bind("<Double-Button-1>", lambda _e, idx=i: launch(state["matches"][idx]))
            state["tiles"].append((tile, color))
        update_selection()
        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        ensure_visible(state["index"])

    def select(idx: int):
        if not state["matches"]:
            return
        state["index"] = max(0, min(idx, len(state["matches"]) - 1))
        update_selection()
        ensure_visible(state["index"])

    def update_selection():
        for i, (tile, _color) in enumerate(state["tiles"]):
            tile.config(highlightbackground=ACCENT if i == state["index"] else BG)

    def ensure_visible(idx: int):
        if not state["tiles"]:
            return
        grid_height = inner.winfo_height()
        if grid_height <= 2 or canvas.winfo_height() <= 2:
            return
        tile = state["tiles"][idx][0]
        y1, y2 = tile.winfo_y(), tile.winfo_y() + TILE_H + 18
        top_px = canvas.yview()[0] * grid_height
        bottom_px = canvas.yview()[1] * grid_height
        if y1 < top_px:
            canvas.yview_moveto(max(0, y1) / grid_height)
        elif y2 > bottom_px:
            canvas.yview_moveto(min(1, max(0, y2 - (bottom_px - top_px))) / grid_height)

    def move(delta: int):
        if not state["matches"]:
            return "break"
        index = state["index"] + delta
        if index < 0:
            index = len(state["matches"]) - 1
        elif index >= len(state["matches"]):
            index = 0
        select(index)
        return "break"

    def launch(entry: dict):
        if entry["type"] == "url":
            webbrowser.open(entry["command"])
            status.config(text=f"opened in browser: {entry['name']}")
            return
        cwd = entry.get("cwd")
        try:
            subprocess.Popen(
                entry["command"],
                shell=True,
                cwd=str(Path(cwd).expanduser()) if cwd else None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            status.config(text=f"launched: {entry['name']}")
        except OSError as exc:
            status.config(text=f"error: {exc}")

    def run_selected(_event=None):
        if state["matches"]:
            launch(state["matches"][min(state["index"], len(state["matches"]) - 1)])
        return "break"

    def on_key(event):
        if event.widget is search:
            return None
        sym = event.keysym
        if sym == "Escape":
            root.destroy()
            return "break"
        if sym == "Up":
            return move(-COLS)
        if sym == "Down":
            return move(COLS)
        if sym == "Left":
            return move(-1)
        if sym == "Right":
            return move(1)
        if sym in ("Return", "KP_Enter"):
            return run_selected(event)
        if sym == "Home":
            return select(0) or "break"
        if sym == "End":
            return select(len(state["matches"]) - 1) or "break"
        if sym == "Prior":
            canvas.yview_scroll(-1, "pages")
            return "break"
        if sym == "Next":
            canvas.yview_scroll(1, "pages")
            return "break"
        if len(event.char) == 1 and event.char.isprintable() and event.char not in "\t":
            search.focus_set()
            search.insert("end", event.char)
            return "break"
        return None

    def on_wheel(event):
        if getattr(event, "delta", 0):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        else:
            canvas.yview_scroll(-1 if event.num == 4 else 1, "units")

    root.bind("<Key>", on_key)
    search.bind("<Return>", run_selected)
    search.bind("<Down>", lambda _e: move(COLS))
    search.bind("<Up>", lambda _e: move(-COLS))
    search.bind("<Escape>", lambda _e: root.destroy())
    search_var.trace_add("write", refresh)
    canvas.bind_all("<MouseWheel>", on_wheel)
    canvas.bind_all("<Button-4>", on_wheel)
    canvas.bind_all("<Button-5>", on_wheel)
    canvas.bind("<Configure>", lambda _e: canvas.itemconfigure(inner_window, width=canvas.winfo_width()))
    inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

    search.focus_set()
    refresh()
    tick()
    if weather_config:
        fetch_weather_async(root, weather_label, weather_config)
    root.mainloop()
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
    icon = input("tile glyph, e.g. a letter or emoji (enter = first letter): ").strip()
    color = input("tile color as #rrggbb (enter = default): ").strip()
    entry = normalize(
        {"name": name, "command": command, "type": etype, "cwd": cwd, "tags": tags, "icon": icon, "color": color},
        len(entries),
    )
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
    windowed = sys.stdout is None
    force_utf8_output()
    parser = argparse.ArgumentParser(description="Universal launcher: apps, commands, scripts, URLs")
    parser.add_argument("name", nargs="?", help="run the first entry matching this name")
    parser.add_argument("--config", type=Path, default=None, help="config file (default: launchers.json beside script, else ~/.config/universal-launcher/launchers.json)")
    parser.add_argument("--list", action="store_true", help="list entries")
    parser.add_argument("--add", action="store_true", help="add an entry interactively")
    parser.add_argument("--gui", action="store_true", help="open the dashboard window (default for the windowed EXE)")
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
    if args.gui or (getattr(sys, "frozen", False) and windowed):
        return launch_gui(entries, path, load_weather_config(path))
    return interactive(entries, path)


if __name__ == "__main__":
    sys.exit(main())
