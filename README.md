# focus-mask

Screen focus overlay tool for Windows (and Linux/X11). Dims everything above and below a horizontal bar that tracks the mouse cursor vertically, helping you read line-by-line without distraction.

No browser extension, no per-app setup — overlays the entire screen at the OS level.

---

## Files

| File | Description |
|------|-------------|
| `focus_mask.py` | Main app: full-screen overlay window, floating control panel, system tray icon |
| `requirements.txt` | Python dependencies (PyQt5 only) |
| `README.md` | This file |

Settings are auto-saved to:
- **Windows:** `%APPDATA%\focus-mask\settings.json`
- **Linux:** `~/.config/focus-mask/settings.json`

---

## Requirements

- Python 3.8+
- PyQt5 ≥ 5.15

---

## Setup

```bash
pip install -r requirements.txt
```

---

## Run

```bash
# Linux / VM
python3 focus_mask.py

# Windows
python focus_mask.py
```

---

## Controls

| Control | Range | Default | Effect |
|---------|-------|---------|--------|
| Dimming (%) | 0–100 | 75 | Opacity of the dark bands above/below the bar |
| Bar height (px) | 30–600 | 120 | Height of the focus bar |
| Brightness | −50–+50 | 0 | Darkens (<0) or brightens (>0) the bar area |
| Tint opacity (%) | 0–50 | 0 | Blends a warm color tint over the bar |
| Tint color | color picker | #FFF8E1 (warm white) | Color used for tint overlay |
| Lock bar | toggle | off | Freezes bar at current cursor Y position |
| Hide panel | button | — | Hides control panel (reopen via tray icon) |

**System tray:**
- Left-click tray icon → toggle panel visibility
- Right-click → Show/Hide panel | Quit

---

## Packaging as standalone .exe (Windows)

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole focus_mask.py
# Output: dist/focus_mask.exe
```

---

## Notes

- **Wayland (Linux):** Click-through is not supported. Run with `QT_QPA_PLATFORM=xcb python3 focus_mask.py` to use XWayland instead.
- **Multi-monitor:** Currently uses the primary screen only. Multi-monitor support (one overlay per screen) is a planned future addition.
- **Dependencies:** Uses `ctypes` for Windows click-through (no `pywin32` needed).
