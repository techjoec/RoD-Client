# Developer Guide

This document collects technical details, build notes, and troubleshooting tips for contributors and advanced users.

## Tech Overview
- Language/UI: Python (Tkinter) with a simple GUI built for MUD play.
- Core capabilities: ANSI rendering, Telnet/IAC handling, RoD‑friendly defaults, macros, direction pad, echo toggle.
- Layout: top controls (host/port, connect/disconnect, echo, status LEDs), output area with context menu, direction pad, and 10 macro buttons.

## Requirements
- Python 3.12 for both runtime and packaging.
  - Note: Python 3.13 removed `telnetlib`. The client depends on it, so use Python 3.12.
- No external dependencies are required for running from source.

## Run From Source
```
python3 modern_realms_client.py
```
Defaults are friendly to Realms of Despair. Typical connection:
- Host: `realmsofdespair.com`
- Port: `4000`

## Packaging (Windows .exe)
There are two ways to build a standalone executable.

1) Convenience script (recommended on Windows 10/11 with Python 3.12):
```
build_windows_exe.bat
```
Output: `dist\RealmsClient.exe`

2) Using the spec directly:
```
py -m PyInstaller --clean RealmsClient.spec
```

Optional:
- Icon: place `RealmsClient.ico` in the repository root; the spec will pick it up automatically.
- UPX: disabled by default in the spec. If you have UPX installed, enable by setting `upx=True` in the spec.

## Protocol & Rendering Notes
- Telnet negotiation targets RoD behavior:
  - Accepts SGA/ECHO, NAWS (window size), TTYPE, NEW‑ENVIRON, MSSP/MSDP/GMCP (payloads currently ignored).
  - Refuses MXP.
- ANSI rendering:
  - Supports 16/256/truecolor, bold, underline, inverse.
  - Carriage returns update prompts correctly.
  - Renderer buffers across split network chunks to avoid stray sequences (e.g., no literal `m`/`32m` artifacts).

## UI Behavior
- Input focus: kept on the input field; refocused on connect/disconnect and after sending.
- Backscroll: double‑click a line to copy it into the input field.
- Macro buttons: right‑click to edit; macros persist to `macros.json` in the working directory.

## Repository Layout
- `modern_realms_client.py` — main application.
- `core_network.py` — networking and Telnet handling.
- `ansi_renderer.py` — ANSI color/formatting.
- `RealmsClient.spec` — PyInstaller spec for Windows builds.
- `build_windows_exe.bat` — helper script to build on Windows.
- `dist/` — output folder for packaged binaries (e.g., `RealmsClient.exe`).
- `legacy_app/` — historical Windows binary (`realms.exe`). Not maintained; modern client is recommended.
- `tests/` — unit and smoke tests.

## Tests
Run tests with pytest:
```
pytest -q
```
Notable tests:
- `tests/test_core_network.py` — Telnet/IAC handling and NAWS clamping.
- `tests/test_ansi_renderer_unit.py` — palette/extended color and CR behavior.
- `tests/smoke_ansi.py` — basic ANSI smoke tests.
- `tests/smoke_client_network.py` & `tests/run_smoke_net.py` — simple network/client smoke.

## Troubleshooting
- Connection issues: verify host/port and outbound TCP is allowed by your network.
- Visible escape codes (e.g., `m`/`32m`): ensure you’re running a recent build; renderer buffers split sequences.
- Focus issues: click once in the input field; the app tries to maintain focus automatically.
- Python version: ensure 3.12 for both runtime and packaging due to `telnetlib`.

