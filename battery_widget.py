"""
Tiny on-screen battery widget for Windows.
Install once:  pip install psutil
Run:           python battery_widget.py   (or pythonw battery_widget.py for no console window)

Controls: drag with left mouse button (position is remembered), right-click for Settings / Quit.
"""
import json
import os
import sys
import time
import tkinter as tk
import psutil

VERSION = "1.0.0"   # bump this for every release (shown at the bottom of the Settings window)

# ---- Customize here ----------------------------------------------------
HIGH_LIMIT = 80    # while charging: turn red at or above this %
LOW_LIMIT = 20     # while unplugged: turn red at or below this %
REFRESH_MS = 2000  # how often to check the battery
WIDTH, HEIGHT = 200, 70
MONITOR = 2        # default screen: 1 = main monitor, 2 = second (falls back to main if there is no 2nd)
# ------------------------------------------------------------------------

GREEN, RED, BLUE, GREY = "#2ecc71", "#e74c3c", "#3498db", "#444444"

# ---- Saved settings ----------------------------------------------------
# The low limit can only be set between 0 and LOW_MAX, the high limit between HIGH_MIN and 100.
LOW_MAX, HIGH_MIN = 20, 80
SETTINGS_FILE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                             "BatteryWidget", "settings.json")


SAVED_POS = None   # (x, y) where the widget was last dropped; None = use the monitor's corner
REMEMBER_POS = True   # ticked in Settings: reopen where it was dropped; unticked: always bottom-right
APP_NAME = "BatteryWidget"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _num(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def load_settings():
    """Values saved from the Settings window override the defaults above."""
    global LOW_LIMIT, HIGH_LIMIT, MONITOR, SAVED_POS, REMEMBER_POS
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
    except Exception:
        return   # no file yet, or unreadable: keep the defaults
    LOW_LIMIT = _num(data.get("low"), 0, LOW_MAX, LOW_LIMIT)
    HIGH_LIMIT = _num(data.get("high"), HIGH_MIN, 100, HIGH_LIMIT)
    MONITOR = _num(data.get("monitor"), 1, 16, MONITOR)
    REMEMBER_POS = bool(data.get("remember", REMEMBER_POS))
    pos = data.get("pos")
    if isinstance(pos, (list, tuple)) and len(pos) == 2:
        try:
            SAVED_POS = (int(pos[0]), int(pos[1]))
        except (TypeError, ValueError):
            SAVED_POS = None


def save_settings():
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump({"low": LOW_LIMIT, "high": HIGH_LIMIT, "monitor": MONITOR,
                       "remember": REMEMBER_POS,
                       "pos": list(SAVED_POS) if (REMEMBER_POS and SAVED_POS) else None}, f)
    except Exception:
        pass


# ---- Start with Windows (registry "Run" entry for the current user) ----
def startup_command():
    """What Windows should run at login: this .exe, or pythonw + this script."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{exe}" "{os.path.abspath(__file__)}"'


def startup_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except Exception:
        return False


def set_startup(enabled):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    except Exception:
        pass


load_settings()


def already_running():
    """True if another copy of the widget is open, so we never show two."""
    global _mutex
    try:
        import ctypes
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\BatteryWidgetSingleInstance")
        return ctypes.windll.kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return False


if already_running():
    sys.exit(0)

root = tk.Tk()
root.overrideredirect(True)          # no title bar
root.attributes("-topmost", True)    # always on top
root.configure(bg="#111111")
# Place the widget at the bottom-right of a chosen monitor, just above its taskbar
MARGIN = 10   # gap in pixels from the screen edge / taskbar


def get_work_areas():
    """Usable area (screen minus taskbar) of each monitor, main monitor first."""
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    found = []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def callback(hmon, hdc, lprc, lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(info))
        w = info.rcWork
        found.append((info.dwFlags & 1, (w.left, w.top, w.right, w.bottom)))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, proto(callback), 0)
    found.sort(key=lambda m: -m[0])   # main monitor first
    return [area for _, area in found]


def corner_position(monitor):
    """Bottom-right of the chosen monitor, just above its taskbar."""
    try:
        areas = get_work_areas()
        left, top, right, bottom = areas[monitor - 1] if monitor - 1 < len(areas) else areas[0]
        return right - WIDTH - MARGIN, bottom - HEIGHT - MARGIN
    except Exception:
        return root.winfo_screenwidth() - WIDTH - MARGIN, root.winfo_screenheight() - HEIGHT - 60


def position_is_visible(x, y):
    """True if the widget's centre would land on a connected monitor (e.g. 2nd screen unplugged = False)."""
    try:
        cx, cy = x + WIDTH // 2, y + HEIGHT // 2
        return any(l <= cx < r and t <= cy < b for l, t, r, b in get_work_areas())
    except Exception:
        return True


def monitor_of(x, y):
    """1-based number of the monitor the widget (top-left at x, y) is on; MONITOR if it can't tell."""
    try:
        cx, cy = x + WIDTH // 2, y + HEIGHT // 2
        for i, (l, t, r, b) in enumerate(get_work_areas(), start=1):
            if l <= cx < r and t <= cy < b:
                return i
    except Exception:
        pass
    return MONITOR


# open where it was last dropped; otherwise in the chosen monitor's corner
if REMEMBER_POS and SAVED_POS and position_is_visible(*SAVED_POS):
    pos_x, pos_y = SAVED_POS
else:
    pos_x, pos_y = corner_position(MONITOR)
root.geometry(f"{WIDTH}x{HEIGHT}+{pos_x}+{pos_y}")

canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, bg="#111111", highlightthickness=0)
canvas.pack()

TRACK_SIDE, TRACK_MID, MARKER = "#4a4a4a", "#262626", "#e0e0e0"


def fade(hex_color, weight=0.55, bg=(34, 34, 34)):
    """Washed-out version of a colour, used for the 0-LOW and HIGH-100 zones."""
    rgb = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(c * weight + k * (1 - weight)) for c, k in zip(rgb, bg))


def draw_icon(x, y, plugged, color):
    """Small 14x16 status icon with its top-left corner at (x, y).
    Charging = lightning bolt. Disconnected = unplugged plug with a slash."""
    if plugged:
        bolt = [(6, 0), (0, 9), (5, 9), (3, 15), (10, 6), (5, 6), (8, 0)]
        coords = [c for dx, dy in bolt for c in (x + dx, y + dy)]
        canvas.create_polygon(coords, fill=color, outline="")
    else:
        canvas.create_rectangle(x + 2, y + 6, x + 10, y + 11, outline=color, fill=color)   # plug body
        canvas.create_line(x + 4, y + 1, x + 4, y + 6, fill=color, width=2)                # prong
        canvas.create_line(x + 8, y + 1, x + 8, y + 6, fill=color, width=2)                # prong
        canvas.create_line(x + 6, y + 11, x + 6, y + 15, fill=color, width=2)              # cable
        canvas.create_line(x - 1, y + 14, x + 13, y + 1, fill="#111111", width=4)          # slash gap
        canvas.create_line(x - 1, y + 14, x + 13, y + 1, fill=color, width=2)              # slash


charge_start = None   # when the current charging session began


def fmt_duration(seconds):
    """'20m' under an hour, '1h 5m' after that."""
    m = int(seconds // 60)
    return f"{m}m" if m < 60 else f"{m // 60}h {m % 60}m"


after_id = None   # the pending timer for the next update


def schedule():
    global after_id
    after_id = root.after(REFRESH_MS, update)


def refresh():
    """Redraw right now (used after saving settings) without starting a second timer."""
    if after_id is not None:
        root.after_cancel(after_id)
    update()


def update():
    global charge_start
    b = psutil.sensors_battery()
    canvas.delete("all")

    if b is None:
        canvas.create_text(WIDTH / 2, HEIGHT / 2, text="No battery found", fill="white")
        schedule()
        return

    pct, plugged = b.percent, b.power_plugged

    # remember when charging started; reset when unplugged
    if plugged:
        if charge_start is None:
            charge_start = time.time()
    else:
        charge_start = None
    # choose colour and status text
    if plugged and pct >= HIGH_LIMIT:
        color, status = RED, "CHARGING - UNPLUG SOON"
    elif not plugged and pct <= LOW_LIMIT:
        color, status = RED, f"LOW {int(pct)}% - RECHARGE"
    elif plugged:
        color, status = BLUE, "PLUGGED IN - CHARGING"
    else:
        color, status = GREEN, "ON BATTERY"

    # status line, with the charging / disconnected icon right after the text
    status_id = canvas.create_text(8, 12, text=status, fill=color, anchor="w", font=("Segoe UI", 9, "bold"))
    icon_x = canvas.bbox(status_id)[2] + 6
    draw_icon(icon_x, 4, plugged, color)

    # progress bar: three zones (0-LOW, LOW-HIGH, HIGH-100) split by 1px markers
    x0, y0, x1, y1 = 8, 28, WIDTH - 8, 48

    def px(p):
        return x0 + (x1 - x0) * p / 100

    zones = [(0, LOW_LIMIT, TRACK_SIDE, fade(color)),      # side zones: gray track, faded fill
             (LOW_LIMIT, HIGH_LIMIT, TRACK_MID, color),    # middle zone: solid fill
             (HIGH_LIMIT, 100, TRACK_SIDE, fade(color))]
    for start, end, track, fill in zones:
        canvas.create_rectangle(px(start), y0, px(end), y1, outline="", fill=track)
        if pct > start:
            canvas.create_rectangle(px(start), y0, px(min(pct, end)), y1, outline="", fill=fill)

    for limit in (LOW_LIMIT, HIGH_LIMIT):
        canvas.create_line(round(px(limit)), y0, round(px(limit)), y1, fill=MARKER)
    canvas.create_text(WIDTH / 2, (y0 + y1) / 2, text=f"{int(pct)}%", fill="white",
                       font=("Segoe UI", 9, "bold"))

    # bottom line: time info
    if plugged:
        remaining = HIGH_LIMIT - pct
        info = f"{remaining:.0f}% to go until {HIGH_LIMIT}%" if remaining > 0 else f"{HIGH_LIMIT}% target reached"
    else:
        remaining = pct - LOW_LIMIT
        info = f"{remaining:.0f}% left until {LOW_LIMIT}%" if remaining > 0 else f"{LOW_LIMIT}% reached - recharge"
    canvas.create_text(8, 58, text=info, fill="#bbbbbb", anchor="w", font=("Segoe UI", 8))

    # bottom right: how long it has been charging, on the same line as the text above
    if plugged and charge_start is not None:
        canvas.create_text(WIDTH - 8, 58, text=fmt_duration(time.time() - charge_start),
                           fill="#bbbbbb", anchor="e", font=("Segoe UI", 8))

    schedule()


# drag to move (the drop position is remembered), right-click for a menu with Settings / Quit
def start_move(e):
    root._dx, root._dy = e.x, e.y
    root._moved = False

def do_move(e):
    root._moved = True
    root.geometry(f"+{root.winfo_x() + e.x - root._dx}+{root.winfo_y() + e.y - root._dy}")

def end_move(e):
    global SAVED_POS
    if REMEMBER_POS and getattr(root, "_moved", False):   # only when really dragged, and only if remembering
        SAVED_POS = (root.winfo_x(), root.winfo_y())
        save_settings()

canvas.bind("<Button-1>", start_move)
canvas.bind("<B1-Motion>", do_move)
canvas.bind("<ButtonRelease-1>", end_move)
# ---- Settings window (minimal dark style) ------------------------------
UI_BG, UI_FG, UI_MUTED = "#161616", "#ececec", "#8b8b8b"
UI_LINE, UI_CONTROL, UI_ACCENT = "#262626", "#2b2b2b", BLUE
UI_FONT = "Segoe UI"
settings_win = None   # keeps a single settings window open at a time


def _round_rect(c, x0, y0, x1, y1, r, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, **kw)


def _label(parent, text, fg=UI_FG, size=10, bold=False, **kw):
    return tk.Label(parent, text=text, bg=UI_BG, fg=fg,
                    font=(UI_FONT, size, "bold" if bold else "normal"), **kw)


class LimitSlider:
    """A 0-100 slider where only lo..hi can be used; the rest is drawn dimmed and cannot be reached."""
    PAD, W, H = 8, 320, 26

    def __init__(self, parent, lo, hi, value, on_change):
        self.lo, self.hi, self.on_change = lo, hi, on_change
        self.value = max(lo, min(hi, value))
        self.canvas = tk.Canvas(parent, width=self.W, height=self.H, bg=UI_BG,
                                highlightthickness=0, cursor="hand2")
        self.canvas.bind("<Button-1>", self._drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.draw()

    def _x(self, v):
        return self.PAD + (self.W - 2 * self.PAD) * v / 100

    def _drag(self, e):
        v = round((e.x - self.PAD) / (self.W - 2 * self.PAD) * 100)
        self.value = max(self.lo, min(self.hi, v))
        self.draw()
        self.on_change(self.value)

    def draw(self):
        c, y = self.canvas, self.H // 2
        c.delete("all")
        c.create_line(self._x(0), y, self._x(100), y, fill="#222222", width=4, capstyle=tk.ROUND)          # blocked
        c.create_line(self._x(self.lo), y, self._x(self.hi), y, fill="#444444", width=4, capstyle=tk.ROUND)  # usable
        c.create_line(self._x(self.lo), y, self._x(self.value), y, fill=UI_ACCENT, width=4, capstyle=tk.ROUND)
        r = 7
        c.create_oval(self._x(self.value) - r, y - r, self._x(self.value) + r, y + r, fill="white", outline="")


class Toggle:
    """On/off switch."""
    W, H = 40, 22

    def __init__(self, parent, value, on_change=None):
        self.value = bool(value)
        self.on_change = on_change
        self.canvas = tk.Canvas(parent, width=self.W, height=self.H, bg=UI_BG,
                                highlightthickness=0, cursor="hand2")
        self.canvas.bind("<Button-1>", self._flip)
        self.draw()

    def _flip(self, _e):
        self.value = not self.value
        self.draw()
        if self.on_change:
            self.on_change(self.value)

    def draw(self):
        c, W, H = self.canvas, self.W, self.H
        c.delete("all")
        fill = UI_ACCENT if self.value else "#3a3a3a"
        r = H / 2
        c.create_oval(0, 0, H, H, fill=fill, outline=fill)
        c.create_oval(W - H, 0, W, H, fill=fill, outline=fill)
        c.create_rectangle(r, 0, W - r, H, fill=fill, outline=fill)
        cx = W - r if self.value else r
        c.create_oval(cx - 8, r - 8, cx + 8, r + 8, fill="white", outline="")


class Segmented:
    """Small pill with one choice selected, e.g. [ 1 | 2 ]."""

    def __init__(self, parent, options, selected):
        self.options, self.value, self.enabled = options, selected, True
        self.frame = tk.Frame(parent, bg=UI_CONTROL)
        self.labels = []
        for opt in options:
            lab = tk.Label(self.frame, text=opt, font=(UI_FONT, 9, "bold"), padx=12, pady=2, cursor="hand2")
            lab.pack(side="left", padx=2, pady=2)
            lab.bind("<Button-1>", lambda _e, o=opt: self._pick(o))
            self.labels.append((opt, lab))
        self.draw()

    def _pick(self, opt):
        if self.enabled:
            self.value = opt
            self.draw()

    def set_value(self, opt):
        self.value = opt
        self.draw()

    def set_enabled(self, flag):
        self.enabled = flag
        self.draw()

    def draw(self):
        for opt, lab in self.labels:
            on = opt == self.value
            if self.enabled:
                lab.config(bg=UI_ACCENT if on else UI_CONTROL, fg="white" if on else UI_MUTED, cursor="hand2")
            else:   # dimmed and not clickable
                lab.config(bg="#3a3a3a" if on else UI_CONTROL, fg="#777777" if on else "#4d4d4d", cursor="arrow")


class FlatButton:
    """Rounded button; primary = filled with the accent colour."""

    def __init__(self, parent, text, command, primary=False, width=88, height=32):
        self.text, self.command, self.primary, self.w, self.h = text, command, primary, width, height
        self.canvas = tk.Canvas(parent, width=width, height=height, bg=UI_BG,
                                highlightthickness=0, cursor="hand2")
        self.canvas.bind("<Button-1>", lambda _e: self.command())
        self.canvas.bind("<Enter>", lambda _e: self.draw(True))
        self.canvas.bind("<Leave>", lambda _e: self.draw(False))
        self.draw(False)

    def draw(self, hover):
        c = self.canvas
        c.delete("all")
        if self.primary:
            fill, fg = ("#4aa3e0" if hover else UI_ACCENT), "white"
        else:
            fill, fg = ("#363636" if hover else UI_CONTROL), UI_FG
        _round_rect(c, 1, 1, self.w - 1, self.h - 1, 8, fill=fill, outline=fill)
        c.create_text(self.w / 2, self.h / 2, text=self.text, fill=fg, font=(UI_FONT, 9, "bold"))


def dark_title_bar(window):
    """Ask Windows 10/11 for a dark title bar so the window matches. Harmless if unsupported."""
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
    except Exception:
        pass


def open_settings():
    """Settings popup: battery limits, display options and startup, with Cancel / Save."""
    global settings_win
    if settings_win is not None and settings_win.winfo_exists():
        settings_win.lift()
        settings_win.focus_force()
        return
    win = settings_win = tk.Toplevel(root)
    win.withdraw()                      # built hidden, then sized to fit its contents and shown at the end
    win.title("Settings")
    win.configure(bg=UI_BG)
    win.attributes("-topmost", True)
    win.resizable(False, False)
    w = 368

    body = tk.Frame(win, bg=UI_BG)
    body.pack(fill="x", padx=24, pady=(22, 0))

    def section(title, first=False):
        if not first:
            tk.Frame(body, bg=UI_LINE, height=1).pack(fill="x", pady=(20, 0))
        _label(body, title.upper(), fg=UI_MUTED, size=8, bold=True).pack(
            anchor="w", pady=(0 if first else 16, 2))

    def setting_row(title, hint=None):
        """Title (and optional hint) on the left; returns the frame whose right side holds the control."""
        f = tk.Frame(body, bg=UI_BG)
        f.pack(fill="x", pady=(10, 0))
        left = tk.Frame(f, bg=UI_BG)
        left.pack(side="left")
        _label(left, title).pack(anchor="w")
        f.hint = None
        if hint:
            f.hint = _label(left, hint, fg=UI_MUTED, size=8, justify="left")
            f.hint.pack(anchor="w")
        return f

    values = {"low": LOW_LIMIT, "high": HIGH_LIMIT}

    def slider_row(key, title, hint, lo, hi):
        values[key] = max(lo, min(hi, values[key]))
        head = tk.Frame(body, bg=UI_BG)
        head.pack(fill="x", pady=(10, 0))
        _label(head, title).pack(side="left")
        shown = _label(head, f"{values[key]}%", bold=True)
        shown.pack(side="right")
        _label(body, hint, fg=UI_MUTED, size=8).pack(anchor="w")

        def changed(v):
            values[key] = v
            shown.config(text=f"{v}%")

        LimitSlider(body, lo, hi, values[key], changed).canvas.pack(anchor="w", pady=(2, 0))

    # --- Battery ---
    section("Battery", first=True)
    slider_row("low", "Low battery alert", f"Red when unplugged  -  adjustable 0 to {LOW_MAX}%", 0, LOW_MAX)
    slider_row("high", "Charge limit", f"Red while charging  -  adjustable {HIGH_MIN} to 100%", HIGH_MIN, 100)

    # --- Display ---
    section("Display")
    try:
        screen_count = max(1, len(get_work_areas()))
    except Exception:
        screen_count = 1
    current_screen = min(monitor_of(root.winfo_x(), root.winfo_y()), screen_count)   # where it is right now
    monitor_pick = None
    mrow = None

    def sync_monitor_row(remember_on):
        """Remembering placement decides the screen by itself, so the picker only works when it is off."""
        if monitor_pick is None:
            return
        monitor_pick.set_enabled(not remember_on)
        mrow.hint.config(text="Follows where you drop it" if remember_on else "Opens in this screen's corner")
        if remember_on:
            monitor_pick.set_value(str(current_screen))    # show the screen it is actually on

    rrow = setting_row("Remember placement", "Off: always opens bottom-right")
    remember_toggle = Toggle(rrow, REMEMBER_POS, on_change=sync_monitor_row)
    remember_toggle.canvas.pack(side="right")

    if screen_count > 1:       # the monitor choice only appears when there is more than one screen
        mrow = setting_row("Monitor", " ")
        monitor_pick = Segmented(mrow, [str(i) for i in range(1, screen_count + 1)],
                                 str(current_screen if REMEMBER_POS else min(MONITOR, screen_count)))
        monitor_pick.frame.pack(side="right")
        sync_monitor_row(REMEMBER_POS)

    # --- System ---
    section("System")
    srow = setting_row("Start with Windows", "Opens when you log in")
    startup_initial = startup_enabled()
    startup_toggle = Toggle(srow, startup_initial)
    startup_toggle.canvas.pack(side="right")

    def save():
        global LOW_LIMIT, HIGH_LIMIT, MONITOR, SAVED_POS, REMEMBER_POS
        LOW_LIMIT, HIGH_LIMIT = values["low"], values["high"]

        REMEMBER_POS = remember_toggle.value
        if not REMEMBER_POS:
            SAVED_POS = None                              # nothing to remember
            if monitor_pick is not None:                  # the monitor choice only applies when not remembering
                MONITOR = int(monitor_pick.value)
                if MONITOR != current_screen:             # a different screen was picked: move there now
                    x, y = corner_position(MONITOR)
                    root.geometry(f"+{x}+{y}")

        if startup_toggle.value != startup_initial:
            set_startup(startup_toggle.value)

        save_settings()
        win.destroy()
        refresh()          # the widget picks up the new settings straight away

    # --- footer ---
    tk.Frame(win, bg=UI_LINE, height=1).pack(fill="x", padx=24, pady=(22, 0))
    bar = tk.Frame(win, bg=UI_BG)
    bar.pack(fill="x", padx=24, pady=(14, 0))
    FlatButton(bar, "Save", save, primary=True).canvas.pack(side="right")
    FlatButton(bar, "Cancel", win.destroy).canvas.pack(side="right", padx=(0, 8))
    _label(win, f"v{VERSION}  ·  Created by Sanjeev Beekeeper", fg="#5f5f5f", size=8).pack(pady=(14, 14))

    # size the window to fit its rows, centre it on the main (1st) monitor, then show it
    win.update_idletasks()
    h = win.winfo_reqheight()
    try:
        l, t, r, bt = get_work_areas()[0]
        x, y = l + (r - l - w) // 2, t + (bt - t - h) // 2
    except Exception:
        x, y = (root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")
    dark_title_bar(win)
    win.deiconify()


class PopupMenu:
    """Minimal dark right-click menu that matches the Settings window."""

    def __init__(self):
        self.win = None

    def close(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None

    def _focus_lost(self):
        # only close if the focus really left this popup (e.g. user clicked another app)
        try:
            if self.win is not None and self.win.focus_get() is None:
                self.close()
        except Exception:
            self.close()

    def show(self, x, y, items):
        """items: list of (text, command, is_danger). Opens at the pointer, kept inside the screen."""
        self.close()
        win = self.win = tk.Toplevel(root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#333333")                       # 1px outline
        inner = tk.Frame(win, bg=UI_BG)
        inner.pack(padx=1, pady=1)
        tk.Frame(inner, bg=UI_BG, height=4).pack()

        def add_item(text, command, danger):
            lab = tk.Label(inner, text=text, bg=UI_BG, fg=UI_FG, font=(UI_FONT, 10),
                           anchor="w", width=15, padx=14, pady=6, cursor="hand2")
            lab.pack(fill="x", padx=4)
            hover_fg = RED if danger else UI_FG
            lab.bind("<Enter>", lambda _e: lab.config(bg="#262626", fg=hover_fg))
            lab.bind("<Leave>", lambda _e: lab.config(bg=UI_BG, fg=UI_FG))
            lab.bind("<Button-1>", lambda _e: (self.close(), root.after(10, command)))

        for i, (text, command, danger) in enumerate(items):
            if i:
                tk.Frame(inner, bg=UI_LINE, height=1).pack(fill="x", padx=14, pady=2)
            add_item(text, command, danger)
        tk.Frame(inner, bg=UI_BG, height=4).pack()

        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        try:   # keep the menu inside the screen the click happened on
            areas = get_work_areas()
            l, t, r, b = next((a for a in areas if a[0] <= x < a[2] and a[1] <= y < a[3]), areas[0])
        except Exception:
            l, t, r, b = 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
        px = x if x + w <= r else x - w                   # flip left / up when near the right or bottom edge
        py = y if y + h <= b else y - h
        win.geometry(f"+{max(l, px)}+{max(t, py)}")
        win.bind("<FocusOut>", lambda _e: win.after(80, self._focus_lost))
        win.bind("<Escape>", lambda _e: self.close())
        win.deiconify()
        win.lift()
        win.focus_force()


popup = PopupMenu()
canvas.bind("<Button-1>", lambda e: popup.close(), add="+")     # clicking the widget dismisses the menu
canvas.bind("<Button-3>", lambda e: popup.show(
    e.x_root, e.y_root, [("Settings", open_settings, False), ("Quit", root.destroy, True)]))

update()
root.mainloop()
