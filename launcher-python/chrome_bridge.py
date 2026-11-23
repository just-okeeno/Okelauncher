"""Windows bridge to control a real Chrome window from the Oke OS overlay.

ctypes port of ChromeOverlayBridge.hpp:
- Find the top-level Chrome window (class "Chrome_WidgetWin_1")
- Back / Forward / Reload via WM_APPCOMMAND (APPCOMMAND_BROWSER_*)
- Language via Chrome's "Local State" JSON (intl.app_locale) and/or --lang launch flag
- Chrome exe discovery (Program Files, LOCALAPPDATA)

Every public function returns a dict and never raises.
"""

import json
import os
import subprocess
from pathlib import Path

SUPPORTED_LANGS = ("en", "es", "fr", "de", "pt", "nl")
WM_APPCOMMAND = 0x0319
APPCOMMAND = {"back": 1, "forward": 2, "reload": 3}  # BROWSER_BACKWARD/FORWARD/REFRESH

_CHROME_EXE_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def _user32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM
    return user32


def chrome_status() -> dict:
    if os.name != "nt":
        return {"supported": False, "chrome_running": False, "installed": False,
                "error": "chrome control requires Windows"}
    return {
        "supported": True,
        "chrome_running": bool(find_chrome_window()),
        "installed": bool(find_chrome_exe()),
    }


def find_chrome_window():
    if os.name != "nt":
        return None
    user32 = _user32()
    hwnd = None
    while True:
        hwnd = user32.FindWindowExW(None, hwnd, "Chrome_WidgetWin_1", None)
        if not hwnd:
            return None
        if user32.IsWindowVisible(hwnd):
            return hwnd


def find_chrome_exe() -> str:
    for candidate in _CHROME_EXE_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = str(Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe")
        if Path(candidate).is_file():
            return candidate
    return "chrome.exe"


def local_state_path() -> str:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return ""
    return str(Path(local) / "Google" / "Chrome" / "User Data" / "Local State")


def navigate(action: str) -> dict:
    command = APPCOMMAND.get(str(action).lower())
    if command is None:
        return {"ok": False, "error": "action must be back, forward or reload"}
    if os.name != "nt":
        return {"ok": False, "error": "chrome control requires Windows"}
    hwnd = find_chrome_window()
    if not hwnd:
        return {"ok": False, "error": "chrome window not found"}
    try:
        user32 = _user32()
        user32.SendMessageW(hwnd, WM_APPCOMMAND, int(hwnd), command << 16)
        return {"ok": True, "action": action}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def set_language(lang: str) -> dict:
    lang = str(lang).lower().strip()
    if lang not in SUPPORTED_LANGS:
        return {"ok": False, "error": f"language must be one of {list(SUPPORTED_LANGS)}"}
    path = local_state_path()
    if not path or not Path(path).is_file():
        return {"ok": False, "error": "chrome Local State not found"}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": f"could not read Local State: {exc}"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "unexpected Local State format"}
    intl = data.get("intl")
    intl = intl if isinstance(intl, dict) else {}
    intl["app_locale"] = lang
    data["intl"] = intl
    try:
        Path(path).write_text(json.dumps(data), encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"could not write Local State: {exc}"}
    return {"ok": True, "lang": lang, "note": "restart Chrome to apply"}


def open_chrome(url: str = "", lang: str = "") -> dict:
    if os.name != "nt":
        return {"ok": False, "error": "chrome control requires Windows"}
    cmd = [find_chrome_exe()]
    lang = str(lang).lower().strip()
    if lang:
        if lang not in SUPPORTED_LANGS:
            return {"ok": False, "error": f"language must be one of {list(SUPPORTED_LANGS)}"}
        cmd.append(f"--lang={lang}")
    if url:
        cmd.append(url)
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
