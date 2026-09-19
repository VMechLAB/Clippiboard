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

## License

MIT - DO WHATCHA WANT W IT.
