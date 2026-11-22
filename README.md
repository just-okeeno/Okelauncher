# Oke Launcher — futuristic minimal movie / TV launcher

A borderless, dark, Direct2D-powered Windows launcher that scans your media
folders and starts any movie/TV file with your default player.

No external dependencies — only the Windows SDK (Direct2D, DirectWrite, WIC).

## Build (CMake + PowerShell)

Prerequisites:
- Windows 10/11
- Visual Studio 2022 Build Tools **with "Desktop development with C++"**
  (or a full VS install)
- CMake (bundled with VS Build Tools — run from *Developer PowerShell for VS*,
  or make sure `cmake.exe` is on PATH)

```powershell
cd oke-launcher
.\build.ps1                 # configure + build Release
.\build.ps1 -Run            # build and launch the app
.\build.ps1 -Config Debug   # debug build
.\build.ps1 -Clean -Build   # rebuild from scratch
.\build.ps1 -Package        # zip the exe into dist\OkeLauncher.zip
```

## Point it at your media

First run creates the config file:

```
%LOCALAPPDATA%\OkeLauncher\oke.cfg
```

Edit the `libraries` line to a `;`-separated list of folders (multiple
`libraries=` lines are also accepted):

```
libraries=C:\Users\you\Videos;D:\Movies;E:\TV Shows
```

Save, then press **F5** inside the app to rescan.

### Posters (optional)

For any video, the app looks for a poster image in the same folder (or the
parent one), trying: `poster.jpg/png`, `folder.jpg/png`, `cover.jpg/png`,
`art.jpg/png`. Without a poster, tiles fall back to a minimal monogram card.

## Controls

| Action | Input |
|---|---|
| Filter library | just start typing |
| Clear filter | `Esc` / `Backspace` |
| Play selection | click a tile, or `Enter` |
| Move selection | arrows / `Home` / `End` |
| Scroll | mouse wheel |
| Rescan libraries | `F5` |
| Window controls | custom title bar (drag, resize, snap all work) |

## Layout

```
CMakeLists.txt          CMake build definition
build.ps1               PowerShell build/run/package script
src/main.cpp            the app (single translation unit)
resources/app.rc        version info + icon + manifest references
resources/app.manifest  per-monitor DPI v2 + common controls v6
resources/app.ico       multi-resolution icon
tools/make_icon.py      regenerates app.ico (python tools/make_icon.py)
```

## Notes

- Files are opened via the shell, so your default media player handles them
  (set `.mkv`/`.mp4` etc. to MPC-HC / VLC in Windows Settings to choose one).
- The whole window is rendered with Direct2D; it is DPI aware for
  per-monitor DPI (v2) and uses rounded windows on Windows 11.
