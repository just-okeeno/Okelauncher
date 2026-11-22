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

VALID_THEMES = frozenset({"obsidian", "aurora", "arctic", "sunset"})
THEME_ALIASES = {"midnight": "obsidian", "oled": "obsidian", "sapphire": "aurora"}

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


def dashboard_path() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return base / "dashboard.html"
    return script_base() / "dashboard.html"


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


WEATHER_CODES = {
    0: ("Clear", "\u2600"), 1: ("Mostly clear", "\U0001f324"), 2: ("Partly cloudy", "\u26c5"), 3: ("Overcast", "\u2601"),
    45: ("Fog", "\U0001f32b"), 48: ("Fog", "\U0001f32b"),
    51: ("Light drizzle", "\U0001f326"), 53: ("Drizzle", "\U0001f326"), 55: ("Heavy drizzle", "\U0001f327"),
    61: ("Light rain", "\U0001f326"), 63: ("Rain", "\U0001f327"), 65: ("Heavy rain", "\U0001f327"),
    71: ("Light snow", "\U0001f328"), 73: ("Snow", "\U0001f327"), 75: ("Heavy snow", "\u2744"), 85: ("Snow showers", "\U0001f328"), 86: ("Snow showers", "\u2744"),
    80: ("Light showers", "\U0001f326"), 81: ("Showers", "\U0001f327"), 82: ("Heavy showers", "\U0001f327"),
    95: ("Thunderstorm", "\u26c8"), 96: ("Thunderstorm", "\u26c8"), 99: ("Hail storm", "\u26c8"),
}


def weather_summary(temp: float, code: int, unit: str = "fahrenheit") -> str:
    description, glyph = WEATHER_CODES.get(int(code), ("Weather", "\U0001f321"))
    value = f"{round(temp)}\u00b0F" if unit.lower().startswith("f") else f"{round(temp)}\u00b0C"
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
            location = {"lat": float(lat), "lon": float(lon), "unit": unit}
            if data.get("city"):
                location["city"] = str(data["city"])
            if data.get("country_code"):
                location["country_code"] = str(data["country_code"])
            return location
        except Exception:
            continue
    return {}


def fetch_weather(config: dict) -> dict:
    import urllib.request

    try:
        location = dict(config)
        if "lat" not in location or "lon" not in location:
            detected = geolocate_by_ip()
            if not detected:
                return {"ok": False, "text": "\u2014", "cond": "", "location": "location unknown", "glyph": "\u25cc"}
            for key, value in detected.items():
                location.setdefault(key, value)
        unit = str(location.get("unit", "fahrenheit"))
        params = f"latitude={location['lat']}&longitude={location['lon']}&current=temperature_2m,weather_code"
        params += f"&temperature_unit={'fahrenheit' if unit.lower().startswith('f') else 'celsius'}"
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.load(resp)
        current = data.get("current", {})
        code = int(current.get("weather_code", 0))
        temp = round(float(current["temperature_2m"]))
        description, glyph = WEATHER_CODES.get(code, ("Weather", "\U0001f321"))
        city = str(location.get("city") or "")
        if city and location.get("country_code"):
            city = f"{city}, {location['country_code']}"
        elif not city:
            city = "your location"
        unit_sym = "\u00b0F" if unit.lower().startswith("f") else "\u00b0C"
        return {"ok": True, "text": f"{temp}{unit_sym}", "cond": description, "location": city, "glyph": glyph}
    except Exception:
        return {"ok": False, "text": "\u2014", "cond": "", "location": "weather unavailable", "glyph": "\u25cc"}


def _cpu_load() -> int | None:
    if os.name == "nt":
        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]

        def sample():
            idle, kernel, user = FILETIME(), FILETIME(), FILETIME()

            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
            return (idle, kernel, user)

        def as_int(value: FILETIME) -> int:
            return (value.dwHighDateTime << 32) | value.dwLowDateTime

        idle1, kernel1, user1 = sample()
        time.sleep(0.25)

        idle2, kernel2, user2 = sample()
        idle_delta = as_int(idle2) - as_int(idle1)
        total = (as_int(kernel2) + as_int(user2)) - (as_int(kernel1) + as_int(user1))
        if total <= 0:
            return None
        return max(0, min(100, round(100 * (1 - idle_delta / total))))
    try:
        loads = os.getloadavg()
        return max(0, min(100, round(100 * loads[0] / max(os.cpu_count() or 1, 1))))
    except (OSError, ValueError):
        return None


def system_stats() -> list[tuple]:
    import platform
    import time

    stats: list[tuple] = [
        ("OS", f"{platform.system()} {platform.release()} ({platform.machine()})", None),
        ("CPU cores", str(os.cpu_count() or "unknown"), None),
    ]
    load_pct = _cpu_load()
    if load_pct is not None:
        label = f"{load_pct}% in use"
        if os.name != "nt" and hasattr(os, "getloadavg"):
            try:
                label += f" (load {os.getloadavg()[0]:.2f})"
            except OSError:
                pass
        stats.append(("CPU load", label, load_pct))
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
                stats.append(("RAM", f"{free:.1f} GB free of {total:.1f} GB ({status.dwMemoryLoad}% in use)", int(status.dwMemoryLoad)))
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
                used_pct = max(0, min(100, round(100 * (total - free) / max(total, 0.01))))
                stats.append(("RAM", f"{free:.1f} GB free of {total:.1f} GB ({used_pct}% in use)", used_pct))
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
            used_pct = max(0, min(100, round(100 * (1 - usage.free / max(usage.total, 1)))))
            stats.append((f"Disk {disk_root}", f"{usage.free / (1024 ** 3):.0f} GB free of {usage.total / (1024 ** 3):.0f} GB", used_pct))
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
    print(f"{BOLD}Oke OS{RESET}  {DIM}type to search · ↑↓ select · Enter run · f favorite · q quit{RESET}\n")
    if not matches:
        print(f"{DIM}  no matches for {query!r}{RESET}")
    for i, entry in enumerate(matches):
        marker = "★" if entry["favorite"] else " "
        kind = "url" if entry["type"] == "url" else "sh"
        line = f" {marker} {entry['name']}  {DIM}[{kind}] {entry['command']}{RESET}"
        prefix = f"{CYAN}{BOLD}▸{RESET}" if i == selected else " "
        print(f"{prefix}{line}")
    sys.stdout.flush()


def launch_dashboard(entries: list[dict], path: Path, weather_config: dict | None = None, theme_name: str = "midnight") -> int:
    import http.server
    import urllib.parse

    ui_state = {
        "entries": entries,
        "theme": THEME_ALIASES.get(theme_name, theme_name),
        "stop": threading.Event(),
        "weather": None,
    }
    if ui_state["theme"] not in VALID_THEMES:
        ui_state["theme"] = "obsidian"
    lock = threading.Lock()

    def persist() -> None:
        save_config(path, ui_state["entries"])

    def set_theme_file(theme: str) -> None:
        data = {}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}
        data["$schema"] = "universal-launcher/v1"
        data["theme"] = theme
        data["entries"] = ui_state["entries"]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    class DashboardHandler(http.server.BaseHTTPRequestHandler):
        server_version = "OkeOS/2.4"

        def log_message(self, *_args) -> None:
            pass

        def _json(self, payload: object, code: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 65536:
                return {}
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}
            return data if isinstance(data, dict) else {}

        def do_GET(self) -> None:
            route = urllib.parse.urlparse(self.path).path
            if route == "/" or route == "/index.html":
                try:
                    html = dashboard_path().read_bytes()
                except OSError:
                    self.send_error(500, "dashboard.html missing beside the launcher")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            elif route == "/api/state":
                with lock:
                    payload = {
                        "os": {"name": "Oke OS", "version": "2.4"},
                        "theme": ui_state["theme"],
                        "categories": CATEGORIES,
                        "entries": ui_state["entries"],
                        "history": [item.get("name", "") for item in load_history(history_path(path))],
                    }
                self._json(payload)
            elif route == "/api/stats":
                self._json([[row[0], row[1], int(row[2]) if row[2] is not None else 0] for row in system_stats()])
            elif route == "/api/weather":
                if weather_config is None:
                    self._json({"ok": False, "text": "\u2014", "cond": "", "location": "weather off", "glyph": "\u25cc"})
                    return
                if ui_state["weather"] is None:
                    ui_state["weather"] = fetch_weather(weather_config)
                self._json(ui_state["weather"])
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            route = urllib.parse.urlparse(self.path).path
            body = self._body()
            if route == "/api/launch":
                entry = find_by_name(ui_state["entries"], str(body.get("name", "")))
                if not entry:
                    self._json({"ok": False, "error": f"no entry matches {body.get('name')!r}"})
                    return
                if entry["type"] == "url":
                    webbrowser.open(entry["command"])
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
                    except OSError as exc:
                        self._json({"ok": False, "error": str(exc)})
                        return
                record_history(history_path(path), entry["name"])
                self._json({"ok": True})
            elif route == "/api/favorite":
                entry = find_by_name(ui_state["entries"], str(body.get("name", "")))
                if entry:
                    entry["favorite"] = not entry["favorite"]
                    persist()
                    self._json({"ok": True, "favorite": entry["favorite"]})
                else:
                    self._json({"ok": False, "error": "unknown app"})
            elif route == "/api/remove":
                entry = find_by_name(ui_state["entries"], str(body.get("name", "")))
                if entry:
                    ui_state["entries"].remove(entry)
                    persist()
                self._json({"ok": bool(entry)})
            elif route == "/api/add":
                payload = {k: v for k, v in body.items() if k in ("name", "command", "type", "cwd", "tags", "favorite", "icon", "color")}
                if not payload.get("name") or not payload.get("command"):
                    self._json({"ok": False, "error": "name and command are required"})
                    return
                try:
                    entry = normalize(payload, len(ui_state["entries"]))
                except ValueError as exc:
                    self._json({"ok": False, "error": str(exc)})
                    return
                with lock:
                    ui_state["entries"].append(entry)
                    persist()
                self._json({"ok": True, "entry": entry})
            elif route == "/api/theme":
                theme = str(body.get("theme", "")).lower()
                if theme not in VALID_THEMES:
                    self._json({"ok": False, "error": f"theme must be one of {sorted(VALID_THEMES)}"})
                    return
                with lock:
                    ui_state["theme"] = theme
                    try:
                        set_theme_file(theme)
                    except OSError:
                        self._json({"ok": False, "error": "could not save theme to launchers.json"})
                        return
                self._json({"ok": True})
            elif route == "/api/power":
                command = power_command(str(body.get("action", "")))
                if not command:
                    self._json({"ok": False, "error": "unsupported power action"})
                    return
                subprocess.Popen(command, shell=True)
                self._json({"ok": True})
            elif route == "/api/shutdown":
                ui_state["stop"].set()
                self._json({"ok": True})
            else:
                self.send_error(404)

    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    except OSError as exc:
        sys.exit(f"error: cannot start dashboard server: {exc}")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Oke OS dashboard running at {url}  (Ctrl+C, or Power & Exit > Close launcher, to stop)")
    print("if your browser did not open automatically, copy the address above into a browser tab")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        webbrowser.open_new_tab(url)
    except Exception:
        print("could not open a browser window automatically")
    try:
        while not ui_state["stop"].wait(0.25):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
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
    parser = argparse.ArgumentParser(description="Oke OS: console-grade TV dashboard shell")
    parser.add_argument("name", nargs="?", help="run the first entry matching this name")
    parser.add_argument("--config", type=Path, default=None, help="config file (default: launchers.json beside script, else ~/.config/universal-launcher/launchers.json)")
    parser.add_argument("--list", action="store_true", help="list entries")
    parser.add_argument("--add", action="store_true", help="add an entry interactively")
    parser.add_argument("--gui", action="store_true", help="open the dashboard UI in your web browser (default for the windowed EXE)")
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
        return launch_dashboard(entries, path, resolve_weather_config(path), resolve_theme(path))
    return interactive(entries, path)


if __name__ == "__main__":
    sys.exit(main())
