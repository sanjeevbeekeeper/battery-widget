# Battery Widget

A tiny always-on-top battery overlay for Windows. It shows whether you are plugged in, a charging
progress bar, and turns red when you cross your own limits, so you remember to unplug at 80%
and recharge before the battery runs low.

## Features

- Charging / on-battery status with a small icon
- Progress bar split into three zones (low alert, normal, charge limit) with 1px markers
- Turns red when charging past your charge limit, or on battery below your low alert
- "X% to go until 80%" while charging, "X% left until 20%" on battery
- Charging timer (for example `20m`)
- Settings window (right-click the widget):
  - Low battery alert (0-20%) and charge limit (80-100%) sliders
  - Remember placement, or always open at the bottom-right above the taskbar
  - Choose which monitor to use (shown only when 2 or more screens are connected)
  - Start with Windows
- Drag to move. Single instance: a second copy closes itself.

## Requirements

- Windows 10 or 11
- Python 3.9 or newer (with Tkinter, included in the standard Windows installer)
- A laptop with a battery

## Run it

```
pip install -r requirements.txt
python battery_widget.py
```

Use `pythonw battery_widget.py` to run without a console window.

## Build a single .exe

```
pip install pyinstaller
pyinstaller --onefile --noconsole --icon=battery.ico --name BatteryWidget battery_widget.py
```

The file is created at `dist\BatteryWidget.exe`. Windows SmartScreen may warn about an unsigned app:
choose **More info**, then **Run anyway**.

## Where settings are stored

`%APPDATA%\BatteryWidget\settings.json` holds your limits, monitor, placement and the
remember-placement choice. Delete it to return to the defaults.
"Start with Windows" uses a per-user entry under
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.

## Defaults

Edit the values at the top of `battery_widget.py` (`HIGH_LIMIT`, `LOW_LIMIT`, `MONITOR`, `WIDTH`, `HEIGHT`).

---

Created by Sanjeev Beekeeper
