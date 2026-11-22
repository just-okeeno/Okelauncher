#!/usr/bin/env python3
"""Oke Launcher: TV-style dashboard for apps, media, files, and system control.

Zero third-party dependencies. Works wherever Python 3.9+ runs.

Usage:
    launch.py                 dashboard GUI (windowed EXE) or text menu (terminal)
    launch.py --gui           force the dashboard
    launch.py <name>          run the first entry matching <name> and exit
    launch.py --list          list all entries
    launch.py --add           add a new entry
    launch.py --remove NAME   remove an entry
    launch.py --config FILE   use FILE instead of the default config
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import json
import os
import shutil
import string
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

THEMES = {
    "midnight": {"bg": "#0f1115", "nav": "#12141a", "surface": "#1b1e26", "surface_hi": "#262b36", "fg": "#e8eaed", "dim": "#9aa0a6", "muted": "#5f6368", "accent": "#89b4fa"},
    "oled": {"bg": "#000000", "nav": "#080808", "surface": "#141414", "surface_hi": "#232323", "fg": "#f5f5f5", "dim": "#8c8c8c", "muted": "#4d4d4d", "accent": "#ff5370"},
    "sapphire": {"bg": "#0a0f1e", "nav": "#0d1426", "surface": "#1e293b", "surface_hi": "#334155", "fg": "#e2e8f0", "dim": "#94a3b8", "muted": "#475569", "accent": "#38bdf8"},
}

CATEGORIES = [
    {"title": "My Computer", "glyph": "🖥", "tags": ["system"], "desc": "Access and manage your PC.", "special": "system"},
    {"title": "Movies & TV", "glyph": "🎬", "tags": ["movies", "tv"], "desc": "Organise and play movies and television shows."},
    {"title": "Videos", "glyph": "🎥", "tags": ["videos"], "desc": "Watch videos stored on your computer."},
    {"title": "Music & Audio", "glyph": "🎵", "tags": ["music", "audio"], "desc": "Music player, playlists and audio library."},
    {"title": "Internet & Browser", "glyph": "🌐", "tags": ["browser", "internet"], "desc": "Browse websites and use web applications."},
    {"title": "Gaming", "glyph": "🎮", "tags": ["gaming", "games"], "desc": "Launch installed PC games and emulators."},
    {"title": "Photos & Gallery", "glyph": "🖼", "tags": ["photos", "gallery"], "desc": "Browse pictures, albums and slideshows."},
    {"title": "Files & Storage", "glyph": "📁", "tags": ["files", "storage"], "desc": "Manage folders, drives and USB devices."},
    {"title": "Live TV & Streaming", "glyph": "📺", "tags": ["streaming", "live-tv"], "desc": "Access streaming platforms and TV services."},
    {"title": "Applications", "glyph": "🪟", "tags": ["apps"], "desc": "Launch installed Windows applications.", "all": True},
    {"title": "Downloads", "glyph": "⬇", "tags": ["downloads"], "desc": "Manage downloaded files and transfers."},
    {"title": "Cloud & Network", "glyph": "☁", "tags": ["cloud", "network"], "desc": "Network drives, shared folders and cloud services."},
    {"title": "PC Settings", "glyph": "⚙", "tags": ["settings"], "desc": "System information and configuration.", "special": "system"},
    {"title": "Tools & Utilities", "glyph": "🛠", "tags": ["tools", "utilities"], "desc": "Useful maintenance and diagnostic tools."},
    {"title": "Radio & Podcasts", "glyph": "📻", "tags": ["radio", "podcasts"], "desc": "Listen to internet radio and podcasts."},
    {"title": "Calendar & Clock", "glyph": "🕘", "tags": ["calendar"], "desc": "Clock, calendar, alarms and timers."},
    {"title": "Productivity", "glyph": "📝", "tags": ["productivity"], "desc": "Calculator, notes, documents and office tools."},
    {"title": "Security & Privacy", "glyph": "🛡", "tags": ["security", "privacy"], "desc": "System security and privacy shortcuts."},
    {"title": "Connected Devices", "glyph": "🔌", "tags": ["devices", "bluetooth"], "desc": "Bluetooth, printers, controllers and externals."},
    {"title": "Power & Exit", "glyph": "⏻", "tags": ["power"], "desc": "Sleep, restart, shutdown and close launcher.", "special": "power"},
]


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
        "theme": "midnight",
        "entries": [
            {"name": "Doctor", "type": "shell", "command": "echo launcher works", "icon": "D", "color": "#2d8a54", "tags": ["tools", "diagnostics"], "favorite": True},
            {"name": "Netflix", "type": "url", "command": "https://www.netflix.com", "icon": "N", "color": "#e50914", "tags": ["movies", "tv", "streaming"]},
            {"name": "YouTube", "type": "url", "command": "https://www.youtube.com", "icon": "▶", "color": "#ff0000", "tags": ["videos", "streaming"]},
            {"name": "Prime Video", "type": "url", "command": "https://www.primevideo.com", "icon": "P", "color": "#00a8e1", "tags": ["movies", "tv", "streaming"]},
            {"name": "Spotify", "type": "url", "command": "https://open.spotify.com", "icon": "♫", "color": "#1db954", "tags": ["music", "audio"]},
            {"name": "Twitch", "type": "url", "command": "https://www.twitch.tv", "icon": "T", "color": "#9146ff", "tags": ["gaming", "streaming"]},
            {"name": "GitHub", "type": "url", "command": "https://github.com", "icon": "G", "color": "#24292e", "tags": ["browser", "internet", "tools"]},
            {"name": "TuneIn radio", "type": "url", "command": "https://tunein.com", "icon": "📻", "color": "#0b60a8", "tags": ["radio", "podcasts", "music"]},
            {"name": "Local file server", "type": "shell", "command": "python -m http.server 8642 --bind 127.0.0.1", "icon": "▤", "color": "#5e81ac", "tags": ["files", "network"]},
        ],
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


def resolve_weather_config(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    weather = data.get("weather")
    if weather is False or weather == "off":
        return None
    if isinstance(weather, dict):
        return weather
    return {}


def resolve_theme(path: Path) -> str:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "midnight"
    theme = data.get("theme") if isinstance(data, dict) else None
    return str(theme).lower() if isinstance(theme, str) else "midnight"


def save_config(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current = {}
    payload = {"$schema": "universal-launcher/v1"}
    if isinstance(current, dict):
        for key in ("weather", "theme"):
            if key in current:
                payload[key] = current[key]
    payload["entries"] = entries
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


def history_path(config: Path) -> Path:
    return config.parent / "launcher_history.json"


def load_history(path: Path, limit: int = 12) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)][:limit]


def record_history(history_file: Path, name: str, limit: int = 12) -> None:
    items = [item for item in load_history(history_file) if item.get("name") != name]
    items.insert(0, {"name": name, "at": datetime.datetime.now().isoformat(timespec="seconds")})
    try:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(json.dumps(items[:limit], indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


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


def category_entries(entries: list[dict], category: dict) -> list[dict]:
    if category.get("all"):
        return list(entries)
    wanted = set(category.get("tags", []))
    return [entry for entry in entries if wanted.intersection(entry["tags"])]


def weather_summary(temp: float, code: int, unit: str = "fahrenheit") -> str:
    descriptions = {
        0: ("Clear", "☀"), 1: ("Mostly clear", "🌤"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁"),
        45: ("Fog", "🌫"), 48: ("Fog", "🌫"),
        51: ("Light drizzle", "🌦"), 53: ("Drizzle", "🌦"), 55: ("Heavy drizzle", "🌧"),
        61: ("Light rain", "🌦"), 63: ("Rain", "🌧"), 65: ("Heavy rain", "🌧"),
        71: ("Light snow", "🌨"), 73: ("Snow", "🌨"), 75: ("Heavy snow", "❄"), 85: ("Snow showers", "🌨"), 86: ("Snow showers", "❄"),
        80: ("Light showers", "🌦"), 81: ("Showers", "🌧"), 82: ("Heavy showers", "🌧"),
        95: ("Thunderstorm", "⛈"), 96: ("Thunderstorm", "⛈"), 99: ("Hail storm", "⛈"),
    }
    description, glyph = descriptions.get(int(code), ("Weather", "🌡"))
    value = f"{round(temp)}°F" if unit.lower().startswith("f") else f"{round(temp)}°C"
    return f"{value} {glyph} {description}"


def geolocate_by_ip() -> dict:
    import urllib.request

    for url in ("https://ipwho.is/", "https://ipapi.co/json/"):
        try:
            with urllib.request.urlopen(url, timeout=6) as resp:
                data = json.load(resp)
            lat = data.get("latitude") or data.get("lat")
            lon = data.get("longitude") or data.get("lon")
            if lat is None or lon is None:
                continue
            unit = "fahrenheit" if data.get("country_code") == "US" else "celsius"
            return {"lat": float(lat), "lon": float(lon), "unit": unit}
        except Exception:
            continue
    return {}


def fetch_weather_async(root, label, config: dict) -> None:
    import urllib.request

    def work():
        try:
            location = dict(config)
            if "lat" not in location or "lon" not in location:
                detected = geolocate_by_ip()
                if not detected:
                    return
                for key, value in detected.items():
                    location.setdefault(key, value)
            unit = str(location.get("unit", "fahrenheit"))
            params = f"latitude={location['lat']}&longitude={location['lon']}&current=temperature_2m,weather_code"
            params += f"&temperature_unit={'fahrenheit' if unit.lower().startswith('f') else 'celsius'}"
            url = f"https://api.open-meteo.com/v1/forecast?{params}"
            with urllib.request.urlopen(url, timeout=6) as resp:
                data = json.load(resp)
            current = data.get("current", {})
            text = weather_summary(current["temperature_2m"], current.get("weather_code", 0), unit)
            root.after(0, lambda: label.config(text=text))
        except Exception:
            return

    threading.Thread(target=work, daemon=True).start()


def system_stats() -> list[tuple[str, str]]:
    import platform

    stats: list[tuple[str, str]] = [
        ("OS", f"{platform.system()} {platform.release()} ({platform.machine()})"),
        ("CPU cores", str(os.cpu_count() or "unknown")),
    ]
    if hasattr(os, "getloadavg") and os.name != "nt":
        try:
            loads = os.getloadavg()
            stats.append(("Load average", f"{loads[0]:.2f} / {loads[1]:.2f} / {loads[2]:.2f}"))
        except OSError:
            pass
    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                total = status.ullTotalPhys / (1024 ** 3)
                free = status.ullAvailPhys / (1024 ** 3)
                stats.append(("RAM", f"{free:.1f} GB free of {total:.1f} GB ({status.dwMemoryLoad}% in use)"))
        except (OSError, AttributeError):
            pass
    else:
        try:
            info = {}
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                key, _, rest = line.partition(":")
                info[key.strip()] = rest.strip().split()[0]
            if "MemTotal" in info and "MemAvailable" in info:
                total = float(info["MemTotal"]) / (1024 ** 2)
                free = float(info["MemAvailable"]) / (1024 ** 2)
                stats.append(("RAM", f"{free:.1f} GB free of {total:.1f} GB"))
        except (OSError, IndexError, ValueError):
            pass
    roots: list[str] = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            candidate = f"{letter}:\\"
            if Path(candidate).exists():
                roots.append(candidate)
    else:
        roots.append("/")
        try:
            for line in Path("/proc/mounts").read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[2] in ("ext4", "ext3", "ext2", "xfs", "btrfs", "zfs"):
                    mount = parts[1]
                    if not mount.startswith(("/boot", "/snap", "/mnt/wsl", "/var/lib/docker")):
                        roots.append(mount)
        except OSError:
            pass
    for disk_root in list(dict.fromkeys(roots))[:8]:
        try:
            usage = shutil.disk_usage(disk_root)
            stats.append((f"Disk {disk_root}", f"{usage.free / (1024 ** 3):.0f} GB free of {usage.total / (1024 ** 3):.0f} GB"))
        except (OSError, PermissionError):
            continue
    return stats


def power_command(action: str) -> str | None:
    if os.name == "nt":
        return {
            "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
            "restart": "shutdown /r /t 0",
            "shutdown": "shutdown /s /t 0",
        }.get(action)
    import platform

    if platform.system() == "Darwin":
        return {
            "sleep": "pmset sleepnow",
            "restart": "osascript -e 'tell application \"System Events\" to restart'",
            "shutdown": "osascript -e 'tell application \"System Events\" to shut down'",
        }.get(action)
    return {
        "sleep": "systemctl suspend",
        "restart": "reboot",
        "shutdown": "poweroff",
    }.get(action)


def gpio_key_map() -> dict:
    return {"\r": "enter", "\n": "enter", "\x1b": "esc", "\x7f": "backspace", "\x03": "quit", "\x04": "quit"}


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
        return gpio_key_map().get(ch, ch)
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
            record_history(history_path(path), matches[selected]["name"])
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


def launch_gui(entries: list[dict], path: Path, weather_config: dict | None = None, theme_name: str = "midnight") -> int:
    try:
        import tkinter as tk
        from tkinter import font as tkfont
        from tkinter import messagebox, simpledialog
    except ImportError:
        print("tkinter is not available in this Python build; using the text menu instead")
        return interactive(entries, path)

    T = THEMES.get(theme_name, THEMES["midnight"])
    BG, NAV_BG = T["bg"], T["nav"]
    SURFACE, SURFACE_HI, ACCENT = T["surface"], T["surface_hi"], T["accent"]
    FG, DIM, MUTED = T["fg"], T["dim"], T["muted"]
    ON_COLOR = "#ffffff"

    root = tk.Tk()
    root.title("Oke Launcher")
    root.configure(bg=BG)
    root.geometry("1280x760")
    root.minsize(1020, 620)

    family = tkfont.nametofont("TkDefaultFont").actual("family")
    COLS, TILE_W, TILE_H = 6, 152, 122
    RECENT_COLS, RECENT_W, RECENT_H = 7, 120, 92

    state = {
        "page": "home",
        "tiles": [],
        "index": 0,
        "actions": [],
        "matches": list(entries),
        "canvas": None,
        "fullscreen": False,
    }

    root.rowconfigure(1, weight=1)
    root.columnconfigure(1, weight=1)

    def tick():
        now = datetime.datetime.now()
        clock_label.config(text=now.strftime("%H:%M"))
        date_label.config(text=now.strftime("%A, %B ") + str(now.day))
        root.after(20000, tick)

    top = tk.Frame(root, bg=BG)
    top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=22, pady=(14, 4))
    brand = tk.Label(top, text="OKE LAUNCHER", bg=BG, fg=ACCENT, font=(family, 13, "bold"))
    brand.pack(side="left")

    right_stack = tk.Frame(top, bg=BG)
    weather_label = tk.Label(right_stack, text="", bg=BG, fg=DIM, font=(family, 11))
    clock_label = tk.Label(right_stack, text="", bg=BG, fg=FG, font=(family, 26, "bold"))
    date_label = tk.Label(right_stack, text="", bg=BG, fg=DIM, font=(family, 11))
    weather_label.pack(side="right", anchor="e", padx=(0, 16))
    clock_label.pack(side="right", anchor="n")
    date_label.pack(side="right", anchor="s")

    search_container = tk.Frame(top, bg=BG)
    search_container.place(relx=0.42, rely=0.5, anchor="center")
    search_var = tk.StringVar()
    search = tk.Entry(
        search_container,
        textvariable=search_var,
        bg=SURFACE,
        fg=FG,
        insertbackground=FG,
        relief="flat",
        font=(family, 11),
        width=36,
    )
    search.pack(ipady=6)

    nav_list = ["home", "apps", "favorites", "stats"] + [f"cat:{i}" for i in range(len(CATEGORIES))]
    nav_labels = ["🏠  Home", "🪟  All apps", "★  Favourites", "📊  System monitor"] + [f"{cat['glyph']}  {cat['title']}" for cat in CATEGORIES]

    nav_frame = tk.Frame(root, bg=NAV_BG)
    nav_frame.grid(row=1, column=0, sticky="nsw", padx=(12, 4), pady=(6, 0))
    nav = tk.Listbox(
        nav_frame,
        bg=NAV_BG,
        fg=DIM,
        selectbackground=SURFACE_HI,
        selectforeground=FG,
        activestyle="none",
        relief="flat",
        highlightthickness=0,
        font=(family, 11),
        width=21,
        exportselection=False,
    )
    nav_scroll = tk.Scrollbar(nav_frame, command=nav.yview, width=9, troughcolor=NAV_BG, bg=NAV_BG, bd=0)
    nav.configure(yscrollcommand=nav_scroll.set)
    for label in nav_labels:
        nav.insert("end", label)
    nav.pack(side="left", fill="y", pady=6)
    nav_scroll.pack(side="right", fill="y")

    content = tk.Frame(root, bg=BG)
    content.grid(row=1, column=1, sticky="nsew", padx=(6, 14), pady=(6, 0))

    status_row = tk.Frame(root, bg=BG)
    status_row.grid(row=2, column=0, columnspan=2, sticky="ew", padx=22, pady=(8, 12))
    status = tk.Label(status_row, text="", bg=BG, fg=DIM, anchor="w", font=(family, 10))
    status.pack(side="left", fill="x", expand=True)
    action_bar = tk.Frame(status_row, bg=BG)
    action_bar.pack(side="right")

    def small_button(text, command):
        return tk.Button(
            action_bar,
            text=text,
            command=command,
            bg=SURFACE,
            fg=FG,
            activebackground=ACCENT,
            activeforeground=BG,
            relief="flat",
            padx=12,
            pady=3,
            cursor="hand2",
            font=(family, 10),
        )

    def add_app_dialog():
        name = simpledialog.askstring("Add app", "App name:", parent=root)
        if not name or not name.strip():
            return
        command = simpledialog.askstring("Add app", f"Command or URL for {name.strip()}:", parent=root)
        if not command or not command.strip():
            status.config(text="add cancelled: a command or URL is required")
            return
        icon = (simpledialog.askstring("Add app", "Tile glyph — letter, symbol, or emoji (Enter = first letter):", parent=root) or "").strip()
        color = (simpledialog.askstring("Add app", "Tile color #rrggbb (Enter = default):", parent=root) or "").strip()
        tags = (simpledialog.askstring("Add app", "Category tags, e.g. movies, gaming (Enter = none):", parent=root) or "").strip()
        entry = normalize(
            {"name": name.strip(), "command": command.strip(), "icon": icon, "color": color, "tags": [t.strip() for t in tags.split(",") if t.strip()]},
            len(entries),
        )
        entries.append(entry)
        save_config(path, entries)
        search_var.set("")
        refresh()
        status.config(text=f"added: {entry['name']}")

    def selected_action() -> dict | None:
        if not state["actions"]:
            return None
        return state["actions"][min(state["index"], len(state["actions"]) - 1)]

    def toggle_favorite():
        action = selected_action()
        if action and action.get("entry"):
            entry = action["entry"]
            entry["favorite"] = not entry["favorite"]
            save_config(path, entries)
            refresh()
            status.config(text=f"{entry['name']} {'favorited' if entry['favorite'] else 'unfavorited'}")

    def remove_selected():
        action = selected_action()
        if action and action.get("entry"):
            entry = action["entry"]
            entries.remove(entry)
            save_config(path, entries)
            refresh()
            status.config(text=f"removed: {entry['name']}")

    def toggle_fullscreen():
        state["fullscreen"] = not state["fullscreen"]
        root.attributes("-fullscreen", state["fullscreen"])

    def refresh():
        query = search_var.get().strip()
        state["matches"] = visible_entries(entries, query) if query else list(entries)
        show_page(state["page"])

    def make_scrolled(parent):
        canvas = tk.Canvas(parent, bg=BG, bd=0, highlightthickness=0)
        inner = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        scrollbar = tk.Scrollbar(parent, command=canvas.yview, width=9, troughcolor=BG, bg=BG, bd=0)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        canvas.bind("<Configure>", lambda _e: canvas.itemconfigure(window_id, width=canvas.winfo_width()))
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

        def on_wheel(event):
            if hasattr(event, "delta") and event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", 0) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", 0) == 5:
                canvas.yview_scroll(1, "units")

        root.bind_all("<MouseWheel>", on_wheel)
        root.bind_all("<Button-4>", on_wheel)
        root.bind_all("<Button-5>", on_wheel)
        return canvas, inner

    def launch(entry: dict):
        if entry["type"] == "url":
            webbrowser.open(entry["command"])
            status.config(text=f"opened in browser: {entry['name']}")
        else:
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
                return
        record_history(history_path(path), entry["name"])

    def run_action(action: dict):
        if action.get("entry"):
            launch(action["entry"])
        elif action.get("page"):
            show_page(action["page"])

    def run_selected(_event=None):
        action = selected_action()
        if action:
            run_action(action)
        return "break"

    def add_tile_grid(parent, items, big=True):
        if big:
            width, height, cols = TILE_W, TILE_H, COLS
        else:
            width, height, cols = RECENT_W, RECENT_H, RECENT_COLS
        for i, action in enumerate(items):
            entry = action.get("entry")
            category = action.get("category")
            color = (entry["color"] if entry else "") or SURFACE
            glyph = (entry["icon"] if entry else "") or (category["glyph"] if category else "?")
            label = entry["name"] if entry else (category["title"] if category else "")
            title_fg = ON_COLOR if entry else FG
            tile = tk.Frame(
                parent,
                bg=color,
                width=width,
                height=height,
                highlightthickness=3,
                highlightbackground=BG,
                highlightcolor=ACCENT,
                cursor="hand2",
            )
            tile.pack_propagate(False)
            tk.Label(tile, text=glyph, bg=color, fg=title_fg, font=(family, 26 if big else 20, "bold")).pack(pady=(12 if big else 8, 0))
            tk.Label(tile, text=label, bg=color, fg=title_fg, font=(family, 11 if big else 9, "bold"), wraplength=width - 18).pack(padx=6, pady=(0, 8))
            tile.grid(row=i // cols, column=i % cols, padx=8, pady=8)
            tile.bind("<Enter>", lambda _e, idx=i: select(idx))
            tile.bind("<Button-1>", lambda _e, idx=i: choice(idx))
            tile.bind("<Double-Button-1>", lambda _e, idx=i: choice(idx))
            state["tiles"].append(tile)
            state["actions"].append(action)

    def choice(idx: int):
        if 0 <= idx < len(state["actions"]):
            run_action(state["actions"][idx])

    def update_selection():
        for i, tile in enumerate(state["tiles"]):
            tile.config(highlightbackground=ACCENT if i == state["index"] else BG)

    def select(idx: int):
        if not state["tiles"]:
            return
        state["index"] = max(0, min(idx, len(state["tiles"]) - 1))
        update_selection()
        ensure_visible(state["index"])

    def ensure_visible(idx: int):
        canvas = state["canvas"]
        if canvas is None or not state["tiles"]:
            return
        visible = canvas.winfo_height()
        if visible <= 2:
            return
        grid = state["tiles"][idx].master
        inner_height = max(grid.winfo_reqheight(), visible, 1)
        tile = state["tiles"][idx]
        y1, y2 = tile.winfo_y(), tile.winfo_y() + tile.winfo_height() + 18
        offset = canvas.yview()[0] * inner_height
        if y1 - offset < 0:
            canvas.yview_moveto(max(0, y1 - 8) / inner_height)
        elif y2 - offset > visible:
            canvas.yview_moveto(min(1, max(0.0, y2 - visible + 8)) / inner_height)

    def move(delta: int):
        if not state["tiles"]:
            return "break"
        index = state["index"] + delta
        if index < 0:
            index = len(state["tiles"]) - 1
        elif index >= len(state["tiles"]):
            index = 0
        select(index)
        return "break"

    def heading(parent, text):
        tk.Label(parent, text=text, bg=BG, fg=FG, font=(family, 15, "bold")).pack(anchor="w", padx=6, pady=(4, 6))

    def empty_note(parent, message):
        tk.Label(parent, text=message, bg=BG, fg=MUTED, font=(family, 12), justify="center").pack(pady=42)

    def build_home():
        canvas, inner = make_scrolled(content)
        state["canvas"] = canvas
        heading(inner, "Main menu")
        category_grid = tk.Frame(inner, bg=BG)
        category_grid.pack(fill="x", padx=4)
        add_tile_grid(category_grid, [{"category": category, "page": f"cat:{i}"} for i, category in enumerate(CATEGORIES)], big=True)
        recents = [
            entry
            for name in [item.get("name") for item in load_history(history_path(path))]
            for entry in entries
            if entry["name"] == name
        ][:7]
        if recents:
            heading(inner, "Recently played")
            strip = tk.Frame(inner, bg=BG)
            strip.pack(fill="x", padx=4, pady=(0, 10))
            add_tile_grid(strip, [{"entry": entry} for entry in recents], big=False)
        select(state["index"])

    def build_entries_page(title, items):
        canvas, inner = make_scrolled(content)
        state["canvas"] = canvas
        heading(inner, title)
        grid = tk.Frame(inner, bg=BG)
        grid.pack(fill="both", expand=True, padx=4)
        add_tile_grid(grid, [{"entry": entry} for entry in items], big=True)
        if not items:
            empty_note(inner, "Nothing here yet.\nUse ＋ Add app (bottom right) and tag entries to fill categories.")

    def build_system():
        canvas, inner = make_scrolled(content)
        state["canvas"] = canvas
        heading(inner, "System monitor")
        for name, value in system_stats():
            row = tk.Frame(inner, bg=SURFACE, width=560, height=44)
            row.pack_propagate(False)
            row.pack(fill="x", padx=6, pady=4)
            tk.Label(row, text=name, bg=SURFACE, fg=DIM, font=(family, 11), anchor="w", width=18).pack(side="left", padx=10)
            tk.Label(row, text=value, bg=SURFACE, fg=FG, font=(family, 11), anchor="w").pack(side="left", padx=10)

    def do_power(action: str):
        if action == "exit":
            root.destroy()
            return
        labels = {"sleep": "put this PC to sleep", "restart": "restart", "shutdown": "shut down"}
        if not messagebox.askyesno("Power", f"Really {labels.get(action, action)} now?"):
            status.config(text="power action cancelled")
            return
        command = power_command(action)
        if not command:
            return
        try:
            subprocess.Popen(command, shell=True)
            status.config(text=f"{action} signal sent")
        except OSError as exc:
            status.config(text=f"error: {exc}")

    def build_power():
        state["canvas"] = None
        heading(content, "Power & exit")
        buttons = tk.Frame(content, bg=BG)
        buttons.pack(padx=8, anchor="n")
        for action, glyph, text in [("sleep", "🌙", "Sleep"), ("restart", "🔄", "Restart"), ("shutdown", "⏻", "Shut down"), ("exit", "✕", "Close launcher")]:
            tk.Button(
                buttons,
                text=f"{glyph}  {text}",
                command=lambda a=action: do_power(a),
                bg=SURFACE,
                fg=FG,
                activebackground=ACCENT,
                activeforeground=BG,
                relief="flat",
                font=(family, 13),
                padx=22,
                pady=14,
                cursor="hand2",
            ).pack(side="left", padx=8, pady=8)

    def category_page(index: int):
        category = CATEGORIES[index]
        if category.get("special") == "system":
            build_system()
            return
        if category.get("special") == "power":
            build_power()
            return
        build_entries_page(category["title"], category_entries(entries, category))

    def show_page(key: str):
        state["page"] = key
        state["tiles"], state["actions"] = [], []
        state["index"] = min(state["index"], max(len(state["matches"]) - 1, 0))
        for child in content.winfo_children():
            child.destroy()
        try:
            nav_row = nav_list.index(key)
            nav.selection_clear(0, "end")
            nav.selection_set(nav_row)
            nav.see(nav_row)
        except ValueError:
            pass
        if key == "home":
            build_home()
        elif key == "apps":
            build_entries_page("All apps", state["matches"])
        elif key == "favorites":
            build_entries_page("Favourites", [entry for entry in entries if entry["favorite"]])
        elif key == "stats":
            build_system()
        elif key.startswith("cat:"):
            category_page(int(key.split(":", 1)[1]))

    def on_nav(_event=None):
        selection = nav.curselection()
        if selection:
            show_page(nav_list[selection[0]])

    def on_key(event):
        if event.widget is search:
            return None
        if len(event.char) == 1 and event.char.isprintable() and event.char not in "\t":
            search.focus_set()
            search.insert("end", event.char)
            return "break"
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
            return select(len(state["tiles"]) - 1) or "break"
        if sym == "Prior":
            if state["canvas"] is not None:
                state["canvas"].yview_scroll(-1, "pages")
            return "break"
        if sym == "Next":
            if state["canvas"] is not None:
                state["canvas"].yview_scroll(1, "pages")
            return "break"
        if sym == "F11":
            toggle_fullscreen()
            return "break"
        if sym == "Tab":
            nav.focus_set()
            return "break"
        return None

    search.bind("<Return>", run_selected)
    search.bind("<Down>", lambda _e: nav.focus_set())
    search.bind("<Escape>", lambda _e: root.destroy())
    search_var.trace_add("write", refresh)
    nav.bind("<<ListboxSelect>>", on_nav)
    nav.bind("<Return>", on_nav)
    root.bind("<Key>", on_key)
    root.bind("<F11>", lambda _e: toggle_fullscreen())
    for label_text, command_fn in [
        ("＋ Add app", add_app_dialog),
        ("★ Favorite", toggle_favorite),
        ("✕ Remove", remove_selected),
        ("⛶ Fullscreen", toggle_fullscreen),
        ("Close", root.destroy),
    ]:
        small_button(label_text, command_fn).pack(side="left", padx=(0, 6), pady=(0, 2))
    search.focus_set()
    show_page("home")
    tick()
    if weather_config is not None:
        weather_label.config(text="locating…")
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
    parser = argparse.ArgumentParser(description="Oke Launcher: TV-style dashboard launcher")
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
        return launch_gui(entries, path, resolve_weather_config(path), resolve_theme(path))
    return interactive(entries, path)


if __name__ == "__main__":
    sys.exit(main())
