# Clipboard

A desktop clipboard manager built on PySide6. It watches your system clipboard, keeps a searchable history, and adds manual entries, a reminders calendar with desktop notifications, and an always-on-top sticky note.

Single Python file, backed by SQLite. No server, no account, no network calls — everything stays on your machine.

![screenshot placeholder](screenshot.png)

## Features

- Copy text, code, links, or images — they appear in a history list, newest first, grouped by day. Click a row to copy it back. Re-copying the same content just bumps its timestamp instead of duplicating it.
- **`+ Add`** (`Ctrl+N`) adds an entry manually, without touching your clipboard. Give it a name, an optional description, and optionally force its type (Link/Code/Image) if auto-detection guesses wrong.
- **Reminders**: set a title, description, and due time; get a tray notification when it fires (app must be running, tray is fine).
- **Sticky note**: a small always-on-top note window that persists across restarts, including position.

## Installing

Requires Python 3.9+ and PySide6 (tested on Python 3.12 / PySide6 6.11).

```bash
pip install PySide6
python clipboard_plus.py
```

Or with a virtual environment:

```bash
python -m venv venv
source venv/bin/activate   # venv\Scripts\activate on Windows
pip install PySide6
python clipboard_plus.py
```

The app starts minimised to the tray — double-click the icon to open it.

## Shortcuts

| Action | Shortcut |
|---|---|
| Add to clipboard | `Ctrl+N` |
| Jump to search | `Ctrl+F` |
| Clear search / hide window | `Esc` |
| Copy item back | Click a row |
| Pin / unpin/remove / open link | Right-click a row |
| Open link or GitHub row | Double-click |

Settings, export, reminders, and the sticky note toggle live behind the `···` button, or the tray icon's right-click menu when the window is hidden.

## Where your data lives

~/.clipboard_plus/data.db SQLite database — entries, reminders, sticky note text
~/.clipboard_plus/config.json background image, accent color, dim level, note position


Delete the folder to reset everything; it's recreated with defaults on next launch. Older databases get missing columns added automatically on open, so upgrades shouldn't require deleting anything.

## Known limits

- Reminders only fire while the app is running (tray counts, full quit doesn't).
- History caps at 500 items by default (`max_items` in `config.json`); older unpinned items get trimmed automatically.
- Tray notifications require a system tray. Some Linux setups (GNOME especially) need an AppIndicator extension before the icon appears. Without a tray, the app still runs, just without pop-ups.

## Troubleshooting

**`ModuleNotFoundError: No module named 'PySide6'`** — run `pip install PySide6`.

**Errors after updating** — usually a missing DB column. The app tries to add columns automatically on startup; if that fails, back up and delete `~/.clipboard_plus/data.db` and relaunch (you'll lose history).

**Tray icon missing** — check tray support:

```bash
python -c "from PySide6.QtWidgets import QApplication, QSystemTrayIcon; QApplication([]); print(QSystemTrayIcon.isSystemTrayAvailable())"
```

If this prints `False`, install a tray extension for your desktop — reminders and the tray menu won't work without one.

## Before releasing

1. Replace the placeholder screenshot with a real one showing genuine entries.
2. Pick a version (`v1.0.0` for first stable release, `v0.1.0` for early/rough).
3. Confirm the license (MIT included by default).
4. Consider respecting `XDG_DATA_HOME` on Linux instead of hardcoding `~/.clipboard_plus/`.
5. Test in a clean virtual environment before publishing.

## License

MIT - DO WHATCHA WANT W IT.
