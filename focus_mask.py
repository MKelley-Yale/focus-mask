# focus_mask.py — Screen Focus Overlay Tool
# Full-screen dim overlay with a horizontal focus bar that follows the cursor.
# Controls: dim strength, bar height, bar brightness, bar tint color/opacity.
# Created: March 2026 | Last edited: March 2026

import sys
import os
import json
import ctypes
import platform

from PyQt5.QtWidgets import (
    QApplication, QWidget, QSlider, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QColorDialog, QSystemTrayIcon, QMenu, QAction
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QRect
from PyQt5.QtGui import QPainter, QColor, QPixmap, QPen

# ── Settings ────────────────────────────────────────────────────────────────

def settings_path():
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "focus-mask", "settings.json")
    return os.path.expanduser("~/.config/focus-mask/settings.json")

DEFAULTS = {
    "dim_opacity": 75,       # 0–100
    "bar_height": 120,       # px
    "bar_brightness": 0,     # −50 to +50
    "bar_tint_color": "#FFF8E1",
    "bar_tint_opacity": 0,   # 0–50
    "locked": False,
    "bar_y": 400,
}

def load_settings():
    path = settings_path()
    s = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path) as f:
                s.update(json.load(f))
        except Exception:
            pass
    return s

def save_settings(s):
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(s, f, indent=2)

# ── Overlay ──────────────────────────────────────────────────────────────────

class OverlayWindow(QWidget):
    """Transparent full-screen overlay that dims everything outside the focus bar."""

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.bar_y = self.s["bar_y"]

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        # Poll cursor position at ~60 fps
        self._last_y = -1
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._poll_cursor)
        self._timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_click_through()

    def _apply_click_through(self):
        """Make the overlay pass mouse/keyboard events to windows underneath."""
        if platform.system() == "Windows":
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            WS_EX_TRANSPARENT = 0x20
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT
            )
        else:
            # X11: clear input shape so clicks fall through
            # Requires python-xlib or a ctypes call to libX11/libXext.
            # If unavailable we skip silently — overlay still works visually.
            try:
                import subprocess
                # Use xdotool / xinput is not available everywhere;
                # instead use Qt's own X11 shape extension via ctypes.
                display = ctypes.cdll.LoadLibrary("libX11.so.6")
                shape   = ctypes.cdll.LoadLibrary("libXext.so.6")
                # XShapeCombineRectangles with 0 rects clears the input region
                ShapeInput = 2
                ShapeSet   = 0
                xwin = int(self.winId())
                xdisplay = display.XOpenDisplay(None)
                shape.XShapeCombineRectangles(
                    xdisplay, xwin, ShapeInput, 0, 0,
                    None, 0, ShapeSet, 0
                )
                display.XCloseDisplay(xdisplay)
            except Exception:
                pass  # best-effort on Linux

    def _poll_cursor(self):
        if self.s["locked"]:
            return
        y = QCursor.pos().y()
        if y != self._last_y:
            self._last_y = y
            self.bar_y = y
            self.s["bar_y"] = y
            self.update()

    def refresh(self):
        """Called by control panel when any setting changes."""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()
        bh = self.s["bar_height"]
        by = self.bar_y

        # Clamp so bar stays fully on screen
        half = bh // 2
        bar_top    = max(0, by - half)
        bar_bottom = min(h, by + half)

        # Dim alpha (0–255 from 0–100%)
        dim_a = int(self.s["dim_opacity"] / 100 * 255)
        dim_color = QColor(0, 0, 0, dim_a)

        # Above bar
        if bar_top > 0:
            painter.fillRect(QRect(0, 0, w, bar_top), dim_color)

        # Below bar
        if bar_bottom < h:
            painter.fillRect(QRect(0, bar_bottom, w, h - bar_bottom), dim_color)

        # Bar brightness overlay
        bright = self.s["bar_brightness"]
        if bright != 0:
            if bright > 0:
                # Brighter: white with proportional alpha
                ba = int(bright / 50 * 180)
                painter.fillRect(QRect(0, bar_top, w, bar_bottom - bar_top),
                                  QColor(255, 255, 255, ba))
            else:
                # Darker: black with proportional alpha
                ba = int(-bright / 50 * 180)
                painter.fillRect(QRect(0, bar_top, w, bar_bottom - bar_top),
                                  QColor(0, 0, 0, ba))

        # Bar tint
        tint_opacity = self.s["bar_tint_opacity"]
        if tint_opacity > 0:
            tint_color = QColor(self.s["bar_tint_color"])
            tint_color.setAlpha(int(tint_opacity / 50 * 200))
            painter.fillRect(QRect(0, bar_top, w, bar_bottom - bar_top), tint_color)

        painter.end()

# ── Control Panel ────────────────────────────────────────────────────────────

class ControlPanel(QWidget):
    """Floating dark control panel. Draggable. Always on top."""

    def __init__(self, overlay, settings):
        super().__init__()
        self.overlay = overlay
        self.s = settings
        self._drag_pos = None

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("""
            QWidget { background: transparent; }
            QLabel  { color: #E0E0E0; font-size: 12px; }
            QSlider::groove:horizontal {
                height: 4px; background: #444; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 14px; height: 14px; margin: -5px 0;
                background: #BEB; border-radius: 7px;
            }
            QSlider::sub-page:horizontal { background: #8BC; border-radius: 2px; }
            QPushButton {
                background: #2A2A2E; color: #E0E0E0;
                border: 1px solid #555; border-radius: 5px;
                padding: 4px 10px; font-size: 12px;
            }
            QPushButton:hover  { background: #3A3A3E; }
            QPushButton:checked { background: #446; border-color: #88A; }
        """)

        self._build_ui()
        self.resize(320, self.sizeHint().height())

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # Background panel drawn via paintEvent; layout sits on top
        title = QLabel("Focus Mask")
        title.setStyleSheet("color: #AAFFAA; font-size: 14px; font-weight: bold;")
        outer.addWidget(title)

        # Helper: slider row
        # Returns (slider, value_label)
        def slider_row(label_text, lo, hi, value, step=1):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(115)
            sld = QSlider(Qt.Horizontal)
            sld.setRange(lo, hi)
            sld.setSingleStep(step)
            sld.setValue(value)
            val_lbl = QLabel(str(value))
            val_lbl.setFixedWidth(30)
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(lbl)
            row.addWidget(sld)
            row.addWidget(val_lbl)
            outer.addLayout(row)
            return sld, val_lbl

        # 1. Dimming
        self.sld_dim, self.lbl_dim = slider_row(
            "Dimming (%):", 0, 100, self.s["dim_opacity"])
        self.sld_dim.valueChanged.connect(lambda v: self._update("dim_opacity", v, self.lbl_dim))

        # 2. Bar height
        self.sld_height, self.lbl_height = slider_row(
            "Bar height (px):", 30, 600, self.s["bar_height"])
        self.sld_height.valueChanged.connect(lambda v: self._update("bar_height", v, self.lbl_height))

        # 3. Brightness
        self.sld_bright, self.lbl_bright = slider_row(
            "Brightness:", -50, 50, self.s["bar_brightness"])
        self.sld_bright.valueChanged.connect(lambda v: self._update("bar_brightness", v, self.lbl_bright))

        # 4. Tint opacity
        self.sld_tint, self.lbl_tint = slider_row(
            "Tint opacity (%):", 0, 50, self.s["bar_tint_opacity"])
        self.sld_tint.valueChanged.connect(lambda v: self._update("bar_tint_opacity", v, self.lbl_tint))

        # Tint color picker
        tint_row = QHBoxLayout()
        tint_lbl = QLabel("Tint color:")
        tint_lbl.setFixedWidth(115)
        self.btn_tint = QPushButton()
        self._refresh_tint_button()
        self.btn_tint.clicked.connect(self._pick_tint_color)
        tint_row.addWidget(tint_lbl)
        tint_row.addWidget(self.btn_tint)
        outer.addLayout(tint_row)

        # Lock + Hide row
        btn_row = QHBoxLayout()
        self.btn_lock = QPushButton("Lock bar")
        self.btn_lock.setCheckable(True)
        self.btn_lock.setChecked(self.s["locked"])
        self.btn_lock.toggled.connect(self._toggle_lock)
        self.btn_hide = QPushButton("Hide panel")
        self.btn_hide.clicked.connect(self.hide)
        btn_row.addWidget(self.btn_lock)
        btn_row.addWidget(self.btn_hide)
        outer.addLayout(btn_row)

    def _update(self, key, value, label_widget):
        label_widget.setText(str(value))
        self.s[key] = value
        save_settings(self.s)
        self.overlay.refresh()

    def _toggle_lock(self, checked):
        self.s["locked"] = checked
        self.btn_lock.setText("Unlock bar" if checked else "Lock bar")
        save_settings(self.s)

    def _pick_tint_color(self):
        color = QColorDialog.getColor(QColor(self.s["bar_tint_color"]), self, "Pick tint color")
        if color.isValid():
            self.s["bar_tint_color"] = color.name()
            save_settings(self.s)
            self._refresh_tint_button()
            self.overlay.refresh()

    def _refresh_tint_button(self):
        c = self.s["bar_tint_color"]
        self.btn_tint.setText(c)
        self.btn_tint.setStyleSheet(
            f"background: {c}; color: {'#111' if self._is_light(c) else '#EEE'};"
            "border: 1px solid #555; border-radius: 5px; padding: 4px 10px;"
        )

    @staticmethod
    def _is_light(hex_color):
        """Return True if the color is light (prefer dark text)."""
        c = QColor(hex_color)
        # Perceived luminance
        return (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000 > 128

    def paintEvent(self, event):
        """Draw the dark semi-transparent panel background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(18, 18, 20, 210))
        painter.setPen(QPen(QColor(80, 80, 90), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        painter.end()

    # ── Dragging ──────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

# ── System Tray ──────────────────────────────────────────────────────────────

def make_tray_icon():
    """Draw a 22×22 icon: light bar between two dark bands."""
    px = QPixmap(22, 22)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.fillRect(0, 0, 22, 8,  QColor(30, 30, 30))
    p.fillRect(0, 8, 22, 6,  QColor(220, 220, 180))
    p.fillRect(0, 14, 22, 8, QColor(30, 30, 30))
    p.end()
    from PyQt5.QtGui import QIcon
    return QIcon(px)


def build_tray(app, overlay, panel):
    tray = QSystemTrayIcon(make_tray_icon(), app)
    tray.setToolTip("Focus Mask")

    menu = QMenu()
    act_toggle = QAction("Hide panel", menu)

    def toggle_panel():
        if panel.isVisible():
            panel.hide()
            act_toggle.setText("Show panel")
        else:
            panel.show()
            act_toggle.setText("Hide panel")

    act_toggle.triggered.connect(toggle_panel)
    act_quit = QAction("Quit", menu)
    act_quit.triggered.connect(app.quit)

    menu.addAction(act_toggle)
    menu.addSeparator()
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: toggle_panel()
                           if reason == QSystemTrayIcon.Trigger else None)
    tray.show()
    return tray

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Wayland warning: click-through not supported
    if os.environ.get("WAYLAND_DISPLAY"):
        print(
            "Warning: Wayland detected. Click-through is not supported on Wayland.\n"
            "The overlay will display correctly but mouse events won't pass through.\n"
            "Run with 'QT_QPA_PLATFORM=xcb python3 focus_mask.py' to use XWayland."
        )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running after panel is hidden

    settings = load_settings()

    overlay = OverlayWindow(settings)
    overlay.show()

    panel = ControlPanel(overlay, settings)
    # Position panel near top-right of screen
    screen = QApplication.primaryScreen().geometry()
    panel.move(screen.width() - 340, 60)
    panel.show()

    tray = build_tray(app, overlay, panel)  # noqa: F841  (must stay alive)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
