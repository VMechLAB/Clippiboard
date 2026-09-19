import sys, re, json, sqlite3, hashlib, datetime, webbrowser, base64
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QScrollArea, QFrame, QLabel, QPushButton, QMenu, QSystemTrayIcon,
    QFileDialog, QToolButton, QMessageBox, QDialog, QDialogButtonBox, QSlider,
    QTextEdit, QDateTimeEdit, QListWidget, QListWidgetItem, QPlainTextEdit
)
from PySide6.QtCore import Qt, QBuffer, QIODevice, QTimer, QDateTime, QPoint
from PySide6.QtGui import (
    QIcon, QPixmap, QImage, QKeySequence, QShortcut,
    QColor, QPainter, QFont
)


APP_NAME = "Clipboard"
APP_DIR = Path.home() / ".clipboard_plus"
APP_DIR.mkdir(exist_ok=True)
DB_PATH = APP_DIR / "data.db"
CONFIG_PATH = APP_DIR / "config.json"


THEME = {
    "bg":         "#0f1012",
    "surface":    "#1a1a22",
    "surface_hi": "#2d2d44",
    "border":     "#F1E7E7",
    "border_hi":  "#333342",
    "text":       "#e6e6e8",
    "text_dim":   "#75757e",
    "text_faint": "#474752",
    "accent":     "#6385c0",
    "radius":     "6px",
    "font":       "'Segoe UI Variable', 'Segoe UI', system-ui, sans-serif",
    "mono":       "'Cascadia Mono', 'Consolas', 'Menlo', monospace",
}

ACCENT_PRESETS = [
    "#30518a", "#744624", "#347241",
    "#a1344f", "#3a2d79", "#28746a",
]

DEFAULT_CONFIG = {
    "background": "",
    "overlay": 210,
    "max_items": 500,
    "accent": THEME["accent"],
    "sticky_geometry": None,   # [x, y, w, h]
    "sticky_visible": False,
}


def load_config():
    if CONFIG_PATH.exists():
        try:
            cfg = {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text())}
            THEME["accent"] = cfg.get("accent", THEME["accent"])
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        # Don't crash the app if the config can't be persisted (e.g. disk full,
        # permissions). The previous code let this exception propagate.
        pass


GITHUB_RE = re.compile(r'^https?://(?:www\.)?github\.com/[\w\-\.]+/[\w\-\.]+')
URL_RE = re.compile(r'^https?://\S+$')
EMAIL_RE = re.compile(r'^[\w\.\-\+]+@[\w\.\-]+\.\w+$')
HEX_RE = re.compile(r'^#?[0-9a-fA-F]{6}$')
CODE_RE = re.compile(
    r'(\b(def |class |function |const |let |var |import |from |public '
    r'|private |fn |func |return )|=>|;\s*\n|</?[a-z]+>)'
)


def detect_kind(text):
    t = text.strip()
    if not t:
        return 'text'
    if GITHUB_RE.match(t): return 'github'
    if URL_RE.match(t): return 'link'
    if EMAIL_RE.match(t): return 'email'
    if HEX_RE.match(t): return 'color'
    if '\n' in t and CODE_RE.search(t): return 'code'
    return 'text'


KIND_LABEL = {
    'text': 'Text', 'link': 'Link', 'github': 'GitHub',
    'email': 'Email', 'color': 'Color', 'code': 'Code', 'image': 'Image',
}


def fmt_time(dt):
    now = datetime.datetime.now()
    delta = (now.date() - dt.date()).days
    t = dt.strftime("%H:%M")
    if delta == 0: return f"Today, {t}"
    if delta == 1: return f"Yesterday, {t}"
    if delta < 7: return f"{dt.strftime('%A')}, {t}"
    if dt.year == now.year: return f"{dt.strftime('%b %d')}, {t}"
    return dt.strftime("%b %d, %Y, %H:%M")


def parse_ts(s):
    if not s:
        return datetime.datetime.now()
    if isinstance(s, datetime.datetime):
        return s
    try:
        return datetime.datetime.fromisoformat(str(s))
    except Exception:
        pass
    try:
        return datetime.datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.datetime.now()


def human_size(n):
    n = float(n)
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f"{int(n)} {u}" if u == 'B' else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def make_icon():
    px = QPixmap(64, 64)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(THEME["accent"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(6, 6, 52, 52, 10, 10)
    p.setBrush(QColor(255, 255, 255, 240))
    p.drawRoundedRect(22, 18, 20, 30, 2, 2)
    p.setBrush(QColor(THEME["accent"]))
    p.drawRoundedRect(26, 14, 12, 8, 2, 2)
    p.end()
    return QIcon(px)


def build_qss(t):
    return f"""
    * {{
        font-family: {t['font']};
        color: {t['text']};
        outline: none;
    }}

    QMainWindow, QDialog {{ background: {t['bg']}; }}
    QWidget#bg {{ background: {t['bg']}; }}

    QLabel#brand {{
        font-size: 13px;
        font-weight: 600;
        color: {t['text']};
        padding: 20px 24px 4px 24px;
    }}
    QLabel#tagline {{
        font-size: 11px;
        color: {t['text_faint']};
        padding: 0 24px 20px 24px;
    }}

    QLineEdit#search, QLineEdit#field, QDateTimeEdit#field {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: {t['radius']};
        padding: 9px 12px;
        font-size: 13px;
        color: {t['text']};
        selection-background-color: {t['accent']};
        selection-color: #ffffff;
    }}
    QLineEdit#search:focus, QLineEdit#field:focus, QDateTimeEdit#field:focus {{
        border: 1px solid {t['border_hi']};
        background: {t['surface_hi']};
    }}

    QPlainTextEdit#field, QTextEdit#field {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: {t['radius']};
        padding: 9px 12px;
        font-size: 13px;
        color: {t['text']};
        selection-background-color: {t['accent']};
        selection-color: #ffffff;
    }}

    QToolButton#menuBtn {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: {t['radius']};
        padding: 6px 14px;
        font-size: 13px;
        color: {t['text_dim']};
    }}
    QToolButton#menuBtn:hover {{
        background: {t['surface_hi']};
        color: {t['text']};
    }}

    QToolButton#addBtn {{
        background: {t['accent']};
        border: none;
        border-radius: {t['radius']};
        padding: 6px 14px;
        font-size: 13px;
        color: #ffffff;
        font-weight: 600;
    }}
    QToolButton#addBtn:hover {{
        background: {t['accent']};
    }}

    QPushButton#kindChip {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: 12px;
        padding: 4px 14px;
        font-size: 11.5px;
        color: {t['text_dim']};
    }}
    QPushButton#kindChip:hover {{
        border: 1px solid {t['border_hi']};
        color: {t['text']};
    }}
    QPushButton#kindChip:checked {{
        background: {t['accent']};
        border: 1px solid {t['accent']};
        color: #ffffff;
    }}

    QPushButton#tab {{
        background: transparent;
        border: none;
        padding: 6px 2px;
        margin: 0 10px 0 0;
        font-size: 12.5px;
        color: {t['text_dim']};
        border-bottom: 2px solid transparent;
    }}
    QPushButton#tab:hover {{
        color: {t['text']};
    }}
    QPushButton#tab:checked {{
        color: {t['text']};
        border-bottom: 2px solid {t['accent']};
    }}

    QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}

    QFrame#row {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: {t['radius']};
    }}
    QFrame#row:hover {{
        background: {t['surface_hi']};
        border: 1px solid {t['border_hi']};
    }}

    QLabel#preview {{
        font-size: 13px;
        color: {t['text']};
    }}
    QLabel#previewMono {{
        font-family: {t['mono']};
        font-size: 12px;
        color: {t['text']};
    }}
    QLabel#meta {{
        font-size: 11px;
        color: {t['text_faint']};
    }}
    QLabel#kindLabel {{
        font-size: 11px;
        color: {t['text_dim']};
    }}

    QToolButton#action {{
        background: transparent;
        border: none;
        padding: 4px 8px;
        font-size: 11.5px;
        color: {t['text_faint']};
    }}
    QToolButton#action:hover {{
        color: {t['text']};
    }}

    QMenu {{
        background: {t['surface']};
        border: 1px solid {t['border_hi']};
        border-radius: {t['radius']};
        padding: 5px;
        color: {t['text']};
    }}
    QMenu::item {{
        padding: 7px 22px 7px 12px;
        border-radius: 4px;
        font-size: 12px;
    }}
    QMenu::item:selected {{
        background: {t['surface_hi']};
        color: {t['text']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {t['border']};
        margin: 4px 6px;
    }}

    QListWidget {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: {t['radius']};
        color: {t['text']};
        font-size: 12.5px;
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 8px;
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background: {t['surface_hi']};
        color: {t['text']};
    }}
    QListWidget#reminderList::item {{
        padding: 10px 8px;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {t['border_hi']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t['text_faint']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

    QLabel#stats {{
        color: {t['text_faint']};
        font-size: 11px;
        padding: 10px 24px;
    }}

    QPushButton#dialogBtn {{
        background: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: {t['radius']};
        padding: 6px 14px;
        font-size: 12px;
        color: {t['text']};
    }}
    QPushButton#dialogBtn:hover {{
        background: {t['surface_hi']};
        border: 1px solid {t['border_hi']};
    }}

    QPushButton#dialogBtnAccent {{
        background: {t['accent']};
        border: none;
        border-radius: {t['radius']};
        padding: 6px 14px;
        font-size: 12px;
        color: #ffffff;
        font-weight: 600;
    }}

    QSlider::groove:horizontal {{
        height: 4px;
        background: {t['border']};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {t['accent']};
        width: 14px;
        margin: -6px 0;
        border-radius: 7px;
    }}
    QSlider::sub-page:horizontal {{
        background: {t['accent']};
        border-radius: 2px;
    }}
    """


STICKY_QSS = """
QWidget#stickyRoot {
    background: #f7e98e;
    border: 1px solid #d8c96a;
}
QPlainTextEdit#stickyText {
    background: transparent;
    border: none;
    color: #3a3418;
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 13px;
    padding: 6px;
}
QToolButton#stickyClose {
    background: transparent;
    border: none;
    color: #6b5f2a;
    font-size: 13px;
    font-weight: 700;
    padding: 2px 8px;
}
QToolButton#stickyClose:hover {
    color: #3a3418;
}
QLabel#stickyTitle {
    color: #6b5f2a;
    font-size: 11px;
    font-weight: 600;
    padding-left: 8px;
}
"""


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                kind TEXT NOT NULL,
                content BLOB NOT NULL,
                hash TEXT UNIQUE,
                pinned INTEGER DEFAULT 0,
                copies INTEGER DEFAULT 0,
                name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_pin ON entries(pinned DESC);
            CREATE INDEX IF NOT EXISTS idx_time ON entries(timestamp DESC);

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                due_ts DATETIME NOT NULL,
                notified INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_due ON reminders(due_ts ASC);

            CREATE TABLE IF NOT EXISTS note (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                text TEXT NOT NULL DEFAULT ''
            );
        """)
        self.conn.commit()
        # Migrate older databases that predate the description column.
        cols = [r['name'] for r in self.conn.execute("PRAGMA table_info(reminders)")]
        if 'description' not in cols:
            self.conn.execute(
                "ALTER TABLE reminders ADD COLUMN description TEXT NOT NULL DEFAULT ''"
            )
            self.conn.commit()
        entry_cols = [r['name'] for r in self.conn.execute("PRAGMA table_info(entries)")]
        if 'name' not in entry_cols:
            self.conn.execute("ALTER TABLE entries ADD COLUMN name TEXT NOT NULL DEFAULT ''")
            self.conn.commit()
        if 'description' not in entry_cols:
            self.conn.execute("ALTER TABLE entries ADD COLUMN description TEXT NOT NULL DEFAULT ''")
            self.conn.commit()

    # clipboard entries
    def add(self, type_, kind, content, name='', description=''):
        h = hashlib.sha256(content).hexdigest()
        row = self.conn.execute(
            "SELECT id FROM entries WHERE hash=?", (h,)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE entries SET timestamp=CURRENT_TIMESTAMP, "
                "name=CASE WHEN ?<>'' THEN ? ELSE name END, "
                "description=CASE WHEN ?<>'' THEN ? ELSE description END "
                "WHERE id=?",
                (name, name, description, description, row['id'])
            )
            self.conn.commit()
            return False
        self.conn.execute(
            "INSERT INTO entries (type, kind, content, hash, name, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (type_, kind, content, h, name, description)
        )
        self.conn.commit()
        return True

    def list(self, view='all', search=''):
        where = []
        if view == 'pinned': where.append("pinned=1")
        elif view == 'link': where.append("kind IN ('link','github')")
        elif view == 'code': where.append("kind='code'")
        elif view == 'image': where.append("type='image'")
        sql = "SELECT * FROM entries"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY pinned DESC, timestamp DESC LIMIT 500"
        rows = self.conn.execute(sql).fetchall()
        if search:
            s = search.lower()
            out = []
            for r in rows:
                if r['type'] == 'image':
                    continue
                txt = self.get_content(r['id']).decode('utf-8', 'ignore')
                if s in txt.lower():
                    out.append(r)
            rows = out
        return rows

    def get(self, eid):
        return self.conn.execute(
            "SELECT * FROM entries WHERE id=?", (eid,)
        ).fetchone()

    def get_content(self, eid):
        r = self.conn.execute(
            "SELECT content FROM entries WHERE id=?", (eid,)
        ).fetchone()
        return bytes(r['content']) if r else b''

    def toggle_pin(self, eid):
        self.conn.execute(
            "UPDATE entries SET pinned = 1 - pinned WHERE id=?", (eid,)
        )
        self.conn.commit()

    def bump(self, eid):
        self.conn.execute(
            "UPDATE entries SET copies = copies + 1 WHERE id=?", (eid,)
        )
        self.conn.commit()

    def delete(self, eid):
        self.conn.execute("DELETE FROM entries WHERE id=?", (eid,))
        self.conn.commit()

    def clear_all(self):
        self.conn.execute("DELETE FROM entries")
        self.conn.commit()

    def stats(self):
        r = self.conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(LENGTH(content)),0) s FROM entries"
        ).fetchone()
        return r['c'], r['s']

    def all_rows(self):
        return self.conn.execute("SELECT * FROM entries").fetchall()

    def trim(self, max_items):
        n = self.conn.execute(
            "SELECT COUNT(*) c FROM entries WHERE pinned=0"
        ).fetchone()['c']
        if n <= max_items:
            return
        self.conn.execute("""
            DELETE FROM entries WHERE id IN (
                SELECT id FROM entries WHERE pinned=0
                ORDER BY timestamp ASC LIMIT ?
            )
        """, (n - max_items,))
        self.conn.commit()

    # manual add
    def add_manual(self, text, name='', description=''):
        """Add a piece of text to the clipboard history directly (not from
        the system clipboard), optionally tagged with a name and a
        description. Returns True if a new row was inserted."""
        return self.add('text', detect_kind(text), text.encode('utf-8'),
                         name=name, description=description)

    # reminders / calendar
    def add_reminder(self, text, due_dt, description=''):
        self.conn.execute(
            "INSERT INTO reminders (text, description, due_ts, notified) VALUES (?, ?, ?, 0)",
            (text, description, due_dt.strftime("%Y-%m-%d %H:%M:%S"))
        )
        self.conn.commit()

    def list_reminders(self):
        return self.conn.execute(
            "SELECT * FROM reminders ORDER BY due_ts ASC"
        ).fetchall()

    def delete_reminder(self, rid):
        self.conn.execute("DELETE FROM reminders WHERE id=?", (rid,))
        self.conn.commit()

    def due_reminders(self, now):
        rows = self.conn.execute(
            "SELECT * FROM reminders WHERE notified=0 AND due_ts<=?",
            (now.strftime("%Y-%m-%d %H:%M:%S"),)
        ).fetchall()
        return rows

    def mark_notified(self, rid):
        self.conn.execute(
            "UPDATE reminders SET notified=1 WHERE id=?", (rid,)
        )
        self.conn.commit()

    # ---- sticky note ----
    def get_note(self):
        row = self.conn.execute("SELECT text FROM note WHERE id=1").fetchone()
        return row['text'] if row else ''

    def set_note(self, text):
        self.conn.execute(
            "INSERT INTO note (id, text) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET text=excluded.text",
            (text,)
        )
        self.conn.commit()


class BackgroundWidget(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.pixmap = None
        self.setObjectName("bg")
        self.reload()

    def reload(self):
        path = self.cfg.get("background", "")
        if path and Path(path).exists():
            pm = QPixmap(path)
            self.pixmap = pm if not pm.isNull() else None
        else:
            self.pixmap = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        if self.pixmap:
            scaled = self.pixmap.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
            p.fillRect(rect, QColor(8, 8, 12, int(self.cfg.get("overlay", 210))))
        p.end()


class EntryRow(QFrame):
    def __init__(self, db, row, on_copy, on_pin, on_delete, on_open):
        super().__init__()
        self.db = db
        self.eid = row['id']
        self.kind = row['kind']
        self.type = row['type']
        self.row = row
        self._on_copy = on_copy
        self._on_pin = on_pin
        self._on_delete = on_delete
        self._on_open = on_open

        self.setObjectName("row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(62)

        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 12, 10)
        h.setSpacing(12)

        if self.type == 'image':
            thumb = QLabel()
            img = QImage()
            img.loadFromData(db.get_content(self.eid))
            if not img.isNull():
                thumb.setPixmap(QPixmap.fromImage(img).scaled(
                    40, 40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
            thumb.setFixedSize(40, 40)
            h.addWidget(thumb)

        mid = QVBoxLayout()
        mid.setSpacing(3)
        mid.setContentsMargins(0, 0, 0, 0)

        preview = QLabel(self._preview())
        preview.setObjectName("previewMono" if self.kind == 'code' else "preview")
        preview.setTextFormat(Qt.TextFormat.PlainText)
        preview.setWordWrap(False)
        if self.row['description'] if 'description' in self.row.keys() else '':
            self.setToolTip(self.row['description'])
        mid.addWidget(preview)

        meta = QHBoxLayout()
        meta.setSpacing(6)

        time_lbl = QLabel(fmt_time(parse_ts(row['timestamp'])))
        time_lbl.setObjectName("meta")
        meta.addWidget(time_lbl)

        sep = QLabel("·")
        sep.setObjectName("meta")
        meta.addWidget(sep)

        kind_lbl = QLabel(KIND_LABEL.get(self.kind, 'Text'))
        kind_lbl.setObjectName("kindLabel")
        meta.addWidget(kind_lbl)

        if row['copies'] > 0:
            sep2 = QLabel("·")
            sep2.setObjectName("meta")
            meta.addWidget(sep2)
            c = QLabel(f"{row['copies']} copies")
            c.setObjectName("meta")
            meta.addWidget(c)

        meta.addStretch()
        mid.addLayout(meta)
        h.addLayout(mid, 1)

        pin_btn = QToolButton()
        pin_btn.setObjectName("action")
        pin_btn.setText("Unpin" if row['pinned'] else "Pin")
        pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if row['pinned']:
            pin_btn.setStyleSheet(f"color: {THEME['accent']};")
        pin_btn.clicked.connect(lambda: self._on_pin(self.eid))
        h.addWidget(pin_btn)

        del_btn = QToolButton()
        del_btn.setObjectName("action")
        del_btn.setText("Remove")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self._on_delete(self.eid))
        h.addWidget(del_btn)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)

    def _preview(self):
        name = self.row['name'] if 'name' in self.row.keys() else ''
        if name:
            return name
        if self.type == 'image':
            return "Image"
        raw = self.db.get_content(self.eid)
        one = ' '.join(raw.decode('utf-8', 'ignore').split())
        return one[:160] + ("..." if len(one) > 160 else "")

    def _ctx_menu(self, pos):
        m = QMenu(self)
        m.addAction("Copy", lambda: self._on_copy(self.eid))
        if self.kind in ('link', 'github'):
            m.addAction("Open in browser", lambda: self._on_open(self.eid))
        m.addSeparator()
        m.addAction("Unpin" if self.row['pinned'] else "Pin",
                     lambda: self._on_pin(self.eid))
        m.addAction("Remove", lambda: self._on_delete(self.eid))
        m.exec(self.mapToGlobal(pos))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_copy(self.eid)

    def mouseDoubleClickEvent(self, e):
        if self.kind in ('link', 'github'):
            self._on_open(self.eid)


class AppearanceDialog(QDialog):
    def __init__(self, cfg, parent):
        super().__init__(parent)
        self.cfg = cfg
        self.parent_win = parent
        self.setWindowTitle("Appearance")
        self.setMinimumWidth(420)
        self.setStyleSheet(parent.styleSheet())

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(16)

        bg_title = QLabel("Background")
        bg_title.setStyleSheet(f"color: {THEME['text']}; font-size: 12px; font-weight: 600;")
        v.addWidget(bg_title)

        bg_row = QHBoxLayout()
        bg_row.setSpacing(8)

        self.bg_label = QLabel(self._bg_name())
        self.bg_label.setStyleSheet(f"color: {THEME['text_dim']}; font-size: 12px;")
        bg_row.addWidget(self.bg_label, 1)

        choose = QPushButton("Choose")
        choose.setObjectName("dialogBtn")
        choose.setCursor(Qt.CursorShape.PointingHandCursor)
        choose.clicked.connect(self._choose)
        bg_row.addWidget(choose)

        clear = QPushButton("Clear")
        clear.setObjectName("dialogBtn")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self._clear)
        bg_row.addWidget(clear)
        v.addLayout(bg_row)

        dim_row = QHBoxLayout()
        dim_lbl = QLabel("Dim")
        dim_lbl.setStyleSheet(f"color: {THEME['text_dim']}; font-size: 12px;")
        dim_lbl.setFixedWidth(36)
        dim_row.addWidget(dim_lbl)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(60, 250)
        self.slider.setValue(int(cfg.get("overlay", 210)))
        self.slider.valueChanged.connect(self._on_dim)
        dim_row.addWidget(self.slider, 1)
        v.addLayout(dim_row)

        accent_title = QLabel("Accent color")
        accent_title.setStyleSheet(f"color: {THEME['text']}; font-size: 12px; font-weight: 600; padding-top: 8px;")
        v.addWidget(accent_title)

        self.accent_row_layout = QHBoxLayout()
        self.accent_row_layout.setSpacing(8)
        for hex_ in ACCENT_PRESETS:
            self.accent_row_layout.addWidget(self._swatch(hex_))
        self.accent_row_layout.addStretch()
        v.addLayout(self.accent_row_layout)

        v.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        v.addWidget(btns)

    def _bg_name(self):
        p = self.cfg.get("background", "")
        return Path(p).name if p else "No background image"

    def _swatch(self, hex_):
        btn = QPushButton()
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        active = (hex_.lower() == THEME["accent"].lower())
        border = THEME["text"] if active else THEME["border_hi"]
        btn.setStyleSheet(
            f"QPushButton {{ background: {hex_}; border: 2px solid {border};"
            f"border-radius: 14px; }}"
            f"QPushButton:hover {{ border: 2px solid {THEME['text']}; }}"
        )
        btn.clicked.connect(lambda _, h=hex_: self._set_accent(h))
        return btn

    def _set_accent(self, hex_):
        THEME["accent"] = hex_
        self.cfg["accent"] = hex_
        save_config(self.cfg)
        self.parent_win.apply_theme()
        self._rebuild_swatches()

    def _rebuild_swatches(self):
        for i in reversed(range(self.accent_row_layout.count())):
            item = self.accent_row_layout.takeAt(i)
            w = item.widget()
            if w:
                w.deleteLater()
        for hex_ in ACCENT_PRESETS:
            self.accent_row_layout.addWidget(self._swatch(hex_))
        self.accent_row_layout.addStretch()

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a background image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self.cfg["background"] = path
            save_config(self.cfg)
            self.bg_label.setText(Path(path).name)
            self.parent_win.bg.reload()

    def _clear(self):
        self.cfg["background"] = ""
        save_config(self.cfg)
        self.bg_label.setText("No background image")
        self.parent_win.bg.reload()

    def _on_dim(self, value):
        self.cfg["overlay"] = value
        save_config(self.cfg)
        self.parent_win.bg.reload()


class AddItemDialog(QDialog):
    """Lets the user type or paste something straight into the clipboard
    history without it having to pass through the system clipboard first.
    Every item gets a required name and an optional description, in
    addition to the actual clipboard content."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Add to clipboard")
        self.setMinimumWidth(440)
        self.setStyleSheet(parent.styleSheet())

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(10)

        title = QLabel("New item")
        title.setStyleSheet(f"color: {THEME['text']}; font-size: 12px; font-weight: 600;")
        v.addWidget(title)

        name_lbl = QLabel("Name")
        name_lbl.setStyleSheet(f"color: {THEME['text_dim']}; font-size: 11px;")
        v.addWidget(name_lbl)

        self.name_input = QLineEdit()
        self.name_input.setObjectName("field")
        self.name_input.setPlaceholderText("e.g. Mama's birthday — required")
        self.name_input.setMaxLength(120)
        v.addWidget(self.name_input)

        desc_lbl = QLabel("Description")
        desc_lbl.setStyleSheet(f"color: {THEME['text_dim']}; font-size: 11px; padding-top: 4px;")
        v.addWidget(desc_lbl)

        self.desc_input = QPlainTextEdit()
        self.desc_input.setObjectName("field")
        self.desc_input.setPlaceholderText("Optional — write what you need here")
        self.desc_input.setFixedHeight(70)
        v.addWidget(self.desc_input)

        self.desc_counter = QLabel("0 / 500")
        self.desc_counter.setStyleSheet(f"color: {THEME['text_faint']}; font-size: 10.5px;")
        self.desc_counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        v.addWidget(self.desc_counter)
        self.desc_input.textChanged.connect(self._enforce_desc_limit)

        content_lbl = QLabel("Content")
        content_lbl.setStyleSheet(f"color: {THEME['text_dim']}; font-size: 11px; padding-top: 4px;")
        v.addWidget(content_lbl)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setObjectName("field")
        self.text_edit.setPlaceholderText("Type or paste text here...")
        self.text_edit.setMinimumHeight(120)
        v.addWidget(self.text_edit)

        # Kind chips: let the user tag what this item is instead of relying
        # only on auto-detection. Only one can be active at a time; none
        # active means "auto-detect from the content".
        kind_lbl = QLabel("Type (optional — auto-detected if left blank)")
        kind_lbl.setStyleSheet(f"color: {THEME['text_dim']}; font-size: 11px; padding-top: 4px;")
        v.addWidget(kind_lbl)

        kind_row = QHBoxLayout()
        kind_row.setSpacing(8)
        self.kind_buttons = {}
        for key, label in [('link', 'Link'), ('code', 'Code'), ('image', 'Image')]:
            b = QPushButton(label)
            b.setObjectName("kindChip")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self._set_kind(k))
            kind_row.addWidget(b)
            self.kind_buttons[key] = b
        kind_row.addStretch()
        v.addLayout(kind_row)

        # Shown only when the "Image" chip is active, since an image can't
        # be typed into the text box.
        self.image_row = QHBoxLayout()
        self.image_path_label = QLabel("No image chosen")
        self.image_path_label.setStyleSheet(f"color: {THEME['text_faint']}; font-size: 11px;")
        self.image_row.addWidget(self.image_path_label, 1)
        choose_img_btn = QPushButton("Choose image...")
        choose_img_btn.setObjectName("dialogBtn")
        choose_img_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_img_btn.clicked.connect(self._choose_image)
        self.image_row.addWidget(choose_img_btn)
        self.image_row_widget = QWidget()
        self.image_row_widget.setLayout(self.image_row)
        self.image_row_widget.setVisible(False)
        v.addWidget(self.image_row_widget)

        self._kind_override = None
        self._image_path = None

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c96a6a; font-size: 11px;")
        self.error_label.setVisible(False)
        v.addWidget(self.error_label)

        hint = QLabel("This will also be copied to your system clipboard.")
        hint.setStyleSheet(f"color: {THEME['text_faint']}; font-size: 11px;")
        v.addWidget(hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

        self.name_input.setFocus()

    def _set_kind(self, key):
        # Enforce single-selection (radio-like) behaviour across the chips,
        # and toggling the active chip again returns to auto-detect.
        turning_on = self.kind_buttons[key].isChecked()
        for k, b in self.kind_buttons.items():
            b.setChecked(k == key and turning_on)
        self._kind_override = key if turning_on else None
        is_image = (self._kind_override == 'image')
        self.image_row_widget.setVisible(is_image)
        self.text_edit.setVisible(not is_image)
        self.text_edit.setEnabled(not is_image)

    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose an image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
        )
        if path:
            self._image_path = path
            self.image_path_label.setText(Path(path).name)
            self.image_path_label.setStyleSheet(f"color: {THEME['text']}; font-size: 11px;")

    def _enforce_desc_limit(self):
        text = self.desc_input.toPlainText()
        if len(text) > 500:
            cursor = self.desc_input.textCursor()
            pos = cursor.position()
            trimmed = text[:500]
            self.desc_input.blockSignals(True)
            self.desc_input.setPlainText(trimmed)
            self.desc_input.blockSignals(False)
            cursor.setPosition(min(pos, len(trimmed)))
            self.desc_input.setTextCursor(cursor)
            text = trimmed
        self.desc_counter.setText(f"{len(text)} / 500")

    def _try_accept(self):
        name = self.name_input.text().strip()

        # Restrictions: a name is always required.
        if not name:
            self._show_error("Please give this item a name.")
            self.name_input.setFocus()
            return
        if len(name) > 120:
            self._show_error("Name is too long (120 characters max).")
            self.name_input.setFocus()
            return

        if self._kind_override == 'image':
            if not self._image_path or not Path(self._image_path).exists():
                self._show_error("Please choose an image file.")
                return
        else:
            if not self.text_edit.toPlainText().strip():
                self._show_error("Please type or paste some content.")
                self.text_edit.setFocus()
                return

        self.error_label.setVisible(False)
        self.accept()

    def _show_error(self, msg):
        self.error_label.setText(msg)
        self.error_label.setVisible(True)

    def name(self):
        return self.name_input.text().strip()

    def description(self):
        return self.desc_input.toPlainText().strip()

    def value(self):
        return self.text_edit.toPlainText()

    def kind_override(self):
        return self._kind_override

    def image_path(self):
        return self._image_path


class RemindersDialog(QDialog):
    """A simple calendar / reminders manager. Uses QDateTimeEdit, which has
    a built-in popup calendar, so no extra calendar widget is required."""

    def __init__(self, db, parent):
        super().__init__(parent)
        self.db = db
        self.parent_win = parent
        self.setWindowTitle("Calendar & Reminders")
        self.setMinimumWidth(460)
        self.setMinimumHeight(420)
        self.setStyleSheet(parent.styleSheet())

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)

        title = QLabel("New reminder")
        title.setStyleSheet(f"color: {THEME['text']}; font-size: 12px; font-weight: 600;")
        v.addWidget(title)

        self.text_input = QLineEdit()
        self.text_input.setObjectName("field")
        self.text_input.setPlaceholderText("Title (e.g. Mama's birthday) — required")
        self.text_input.setMaxLength(120)
        v.addWidget(self.text_input)

        self.desc_input = QPlainTextEdit()
        self.desc_input.setObjectName("field")
        self.desc_input.setPlaceholderText(
            "Description (optional) — write what you need here, e.g. "
            "\"Get flowers and call at 6pm, she likes lilies\""
        )
        self.desc_input.setFixedHeight(80)
        v.addWidget(self.desc_input)

        self.desc_counter = QLabel("0 / 500")
        self.desc_counter.setStyleSheet(f"color: {THEME['text_faint']}; font-size: 10.5px;")
        self.desc_counter.setAlignment(Qt.AlignmentFlag.AlignRight)
        v.addWidget(self.desc_counter)
        self.desc_input.textChanged.connect(self._enforce_desc_limit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c96a6a; font-size: 11px;")
        self.error_label.setVisible(False)
        v.addWidget(self.error_label)

        row = QHBoxLayout()
        self.when = QDateTimeEdit()
        self.when.setObjectName("field")
        self.when.setCalendarPopup(True)
        self.when.setDateTime(QDateTime.currentDateTime().addSecs(600))
        self.when.setDisplayFormat("yyyy-MM-dd HH:mm")
        row.addWidget(self.when, 1)

        add_btn = QPushButton("Add reminder")
        add_btn.setObjectName("dialogBtnAccent")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._add)
        row.addWidget(add_btn)
        v.addLayout(row)

        list_title = QLabel("Upcoming")
        list_title.setStyleSheet(f"color: {THEME['text']}; font-size: 12px; font-weight: 600; padding-top: 8px;")
        v.addWidget(list_title)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("reminderList")
        v.addWidget(self.list_widget, 1)

        del_btn = QPushButton("Delete selected")
        del_btn.setObjectName("dialogBtn")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(self._delete_selected)
        v.addWidget(del_btn)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        v.addWidget(btns)

        self._reload()

    def _enforce_desc_limit(self):
        text = self.desc_input.toPlainText()
        if len(text) > 500:
            cursor = self.desc_input.textCursor()
            pos = cursor.position()
            trimmed = text[:500]
            self.desc_input.blockSignals(True)
            self.desc_input.setPlainText(trimmed)
            self.desc_input.blockSignals(False)
            cursor.setPosition(min(pos, len(trimmed)))
            self.desc_input.setTextCursor(cursor)
            text = trimmed
        self.desc_counter.setText(f"{len(text)} / 500")

    def _add(self):
        title = self.text_input.text().strip()
        description = self.desc_input.toPlainText().strip()
        due = self.when.dateTime().toPython()

        # Restrictions: a title is required, it can't be excessively long,
        # and the reminder can't be set in the past.
        if not title:
            self._show_error("Please enter a title for the reminder.")
            self.text_input.setFocus()
            return
        if len(title) > 120:
            self._show_error("Title is too long (120 characters max).")
            self.text_input.setFocus()
            return
        if due < datetime.datetime.now():
            self._show_error("Pick a date and time in the future.")
            self.when.setFocus()
            return

        self.error_label.setVisible(False)
        self.db.add_reminder(title, due, description)
        self.text_input.clear()
        self.desc_input.clear()
        self._reload()

    def _show_error(self, msg):
        self.error_label.setText(msg)
        self.error_label.setVisible(True)

    def _reload(self):
        self.list_widget.clear()
        for r in self.db.list_reminders():
            due = parse_ts(r['due_ts'])
            status = "notified" if r['notified'] else "pending"
            label = f"{due.strftime('%b %d, %Y %H:%M')} — {r['text']} ({status})"
            desc = r['description'] if 'description' in r.keys() else ''
            if desc:
                snippet = desc if len(desc) <= 60 else desc[:60] + "..."
                label += f"\n    {snippet}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, r['id'])
            item.setToolTip(desc if desc else "No description")
            self.list_widget.addItem(item)

    def _delete_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        rid = item.data(Qt.ItemDataRole.UserRole)
        self.db.delete_reminder(rid)
        self._reload()


class StickyNote(QWidget):
    """A tiny always-on-top note window, like a sticky paper note on your
    desktop. Text is auto-saved to the database as you type."""

    def __init__(self, db, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg
        self.setWindowTitle("Sticky Note")
        self.setObjectName("stickyRoot")
        self.setStyleSheet(STICKY_QSS)

        # Frameless-ish but still movable/resizable; stays above all windows.
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 4, 0)
        lbl = QLabel("Note")
        lbl.setObjectName("stickyTitle")
        bar.addWidget(lbl)
        bar.addStretch()
        close_btn = QToolButton()
        close_btn.setObjectName("stickyClose")
        close_btn.setText("×")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        bar.addWidget(close_btn)
        v.addLayout(bar)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setObjectName("stickyText")
        self.text_edit.setPlainText(self.db.get_note())
        self.text_edit.textChanged.connect(self._save)
        v.addWidget(self.text_edit, 1)

        geo = cfg.get("sticky_geometry")
        if geo and len(geo) == 4:
            self.setGeometry(*geo)
        else:
            self.resize(260, 220)

    def _save(self):
        self.db.set_note(self.text_edit.toPlainText())

    def moveEvent(self, e):
        super().moveEvent(e)
        self._save_geometry()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._save_geometry()

    def _save_geometry(self):
        g = self.geometry()
        self.cfg["sticky_geometry"] = [g.x(), g.y(), g.width(), g.height()]
        save_config(self.cfg)

    def closeEvent(self, e):
        # Hide instead of destroying, so the note and its position persist
        # for the rest of the session.
        e.ignore()
        self.hide()
        self.cfg["sticky_visible"] = False
        save_config(self.cfg)

    def showEvent(self, e):
        super().showEvent(e)
        self.cfg["sticky_visible"] = True
        save_config(self.cfg)


class MainWindow(QMainWindow):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.db = Database()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(920, 640)
        self.setMinimumSize(680, 440)

        self.view = 'all'
        self._suppress = False

        self.bg = BackgroundWidget(cfg)
        self.setCentralWidget(self.bg)

        self.sticky = StickyNote(self.db, self.cfg)

        self._build_ui()
        self._build_tray()
        self._setup_clipboard()
        self.apply_theme()

        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            lambda: self.search.setFocus()
        )
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self._add_item)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._clear_search)

        self.refresh()

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(4000)
        self._update_stats()

        # Check for due reminders every 15 seconds and fire a real desktop
        # notification via the system tray icon.
        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start(15000)
        QTimer.singleShot(1000, self._check_reminders)

        QTimer.singleShot(150, self.search.setFocus)

        if cfg.get("sticky_visible"):
            self.sticky.show()

    def apply_theme(self):
        self.setStyleSheet(build_qss(THEME))
        self.setWindowIcon(make_icon())

    def _build_ui(self):
        root = QVBoxLayout(self.bg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        hv = QVBoxLayout(header)
        hv.setContentsMargins(24, 22, 24, 6)
        hv.setSpacing(14)

        brand_row = QHBoxLayout()
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        brand_row.addWidget(brand)
        brand_row.addStretch()

        add_btn = QToolButton()
        add_btn.setObjectName("addBtn")
        add_btn.setText("+ Add")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Add an item to your clipboard history (Ctrl+N)")
        add_btn.clicked.connect(self._add_item)
        brand_row.addWidget(add_btn)

        menu_btn = QToolButton()
        menu_btn.setObjectName("menuBtn")
        menu_btn.setText("···")
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.clicked.connect(self._show_menu)
        brand_row.addWidget(menu_btn)
        hv.addLayout(brand_row)

        tagline = QLabel("Everything you copy, saved and searchable.")
        tagline.setObjectName("tagline")
        hv.addWidget(tagline)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search")
        self.search.textChanged.connect(self.refresh)
        search_row.addWidget(self.search, 1)
        hv.addLayout(search_row)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.tabs = {}
        for key, label in [
            ('all', 'All'), ('pinned', 'Pinned'), ('link', 'Links'),
            ('code', 'Code'), ('image', 'Images'),
        ]:
            b = QPushButton(label)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=key: self.set_view(k))
            tab_row.addWidget(b)
            self.tabs[key] = b
        self.tabs['all'].setChecked(True)
        tab_row.addStretch()
        hv.addLayout(tab_row)

        root.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_inner = QWidget()
        self.cards = QVBoxLayout(self.scroll_inner)
        self.cards.setContentsMargins(24, 12, 24, 8)
        self.cards.setSpacing(6)
        self.scroll.setWidget(self.scroll_inner)
        root.addWidget(self.scroll, 1)

        self.stats = QLabel("")
        self.stats.setObjectName("stats")
        root.addWidget(self.stats)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction("Show / Hide", self._toggle_win)
        m.addAction("Add item...", self._add_item)
        m.addAction("Sticky note", self._toggle_sticky)
        m.addAction("Calendar & Reminders...", self._open_reminders)
        m.addSeparator()
        m.addAction("Quit", QApplication.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(
            lambda r: self._toggle_win()
            if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray.show()

    def _setup_clipboard(self):
        self.clip = QApplication.clipboard()
        self.clip.dataChanged.connect(self._on_clipboard)

    def _on_clipboard(self):
        if self._suppress:
            return
        md = self.clip.mimeData()
        if md.hasText():
            txt = self.clip.text()
            if not txt.strip():
                return
            self.db.add('text', detect_kind(txt), txt.encode('utf-8'))
        elif md.hasImage():
            img = self.clip.image()
            if img.isNull():
                return
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            self.db.add('image', 'image', bytes(buf.data()))
        else:
            return
        self.db.trim(int(self.cfg.get('max_items', 500)))
        self.refresh()

    def set_view(self, key):
        self.view = key
        for k, b in self.tabs.items():
            b.setChecked(k == key)
        self.refresh()

    def _clear_search(self):
        if self.search.text():
            self.search.clear()
        else:
            self.hide()

    def refresh(self):
        while self.cards.count():
            item = self.cards.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        rows = self.db.list(view=self.view, search=self.search.text())
        if not rows:
            self.cards.addWidget(self._empty_state())
            self.cards.addStretch()
            return

        last_day = None
        for r in rows:
            dt = parse_ts(r['timestamp'])
            if dt.date() != last_day:
                gl = QLabel(self._day_label(dt))
                gl.setStyleSheet(
                    f"color: {THEME['text_faint']}; font-size: 10.5px;"
                    f"font-weight: 600; padding: 16px 2px 6px 2px;"
                )
                self.cards.addWidget(gl)
                last_day = dt.date()
            self.cards.addWidget(EntryRow(
                self.db, r,
                on_copy=self._copy, on_pin=self._pin,
                on_delete=self._delete, on_open=self._open,
            ))
        self.cards.addStretch()

    def _day_label(self, dt):
        now = datetime.datetime.now()
        d = (now.date() - dt.date()).days
        if d == 0: return "Today"
        if d == 1: return "Yesterday"
        if d < 7: return dt.strftime("%A")
        if dt.year == now.year: return dt.strftime("%B %d")
        return dt.strftime("%B %d, %Y")

    def _empty_state(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(4)

        title = QLabel("Nothing here yet")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 13px; color: {THEME['text_dim']};")
        v.addWidget(title)

        hint = QLabel("Copy something, or click + Add, and it will show up here.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"font-size: 12px; color: {THEME['text_faint']};")
        v.addWidget(hint)
        v.addSpacing(220)
        return w

    def _copy(self, eid):
        row = self.db.get(eid)
        if not row:
            return
        content = self.db.get_content(eid)
        self._suppress = True
        if row['type'] == 'image':
            img = QImage()
            img.loadFromData(content)
            self.clip.setImage(img)
        else:
            self.clip.setText(content.decode('utf-8', 'ignore'))
        self.db.bump(eid)
        QTimer.singleShot(200, self._release)
        self.refresh()
        self.stats.setText("Copied")
        QTimer.singleShot(1200, self._update_stats)

    def _release(self):
        self._suppress = False

    def _pin(self, eid):
        self.db.toggle_pin(eid)
        self.refresh()

    def _delete(self, eid):
        self.db.delete(eid)
        self.refresh()

    def _open(self, eid):
        content = self.db.get_content(eid).decode('utf-8', 'ignore').strip()
        if content.startswith(('http://', 'https://')):
            webbrowser.open(content)

    def _update_stats(self):
        c, s = self.db.stats()
        self.stats.setText(f"{c} entries · {human_size(s)}")

    def _toggle_win(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def closeEvent(self, e):
        e.ignore()
        self.hide()

    def open_appearance(self):
        AppearanceDialog(self.cfg, self).exec()

    # ---- new features ----
    def _add_item(self):
        dlg = AddItemDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = dlg.name()
        description = dlg.description()
        override = dlg.kind_override()

        if override == 'image':
            path = dlg.image_path()
            try:
                data = Path(path).read_bytes()
            except OSError as ex:
                QMessageBox.warning(self, "Add item", f"Could not read image:\n{ex}")
                return
            img = QImage()
            img.loadFromData(data)
            if img.isNull():
                QMessageBox.warning(self, "Add item", "That file isn't a valid image.")
                return
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            self.db.add('image', 'image', bytes(buf.data()), name=name, description=description)
            self._suppress = True
            self.clip.setImage(img)
            QTimer.singleShot(200, self._release)
        else:
            text = dlg.value()
            if not text.strip():
                return
            kind = override if override else detect_kind(text)
            self.db.add('text', kind, text.encode('utf-8'), name=name, description=description)
            self._suppress = True
            self.clip.setText(text)
            QTimer.singleShot(200, self._release)

        self.db.trim(int(self.cfg.get('max_items', 500)))
        self.refresh()
        self._update_stats()

    def _open_reminders(self):
        RemindersDialog(self.db, self).exec()

    def _toggle_sticky(self):
        if self.sticky.isVisible():
            self.sticky.hide()
        else:
            self.sticky.show()
            self.sticky.raise_()
            self.sticky.activateWindow()

    def _check_reminders(self):
        now = datetime.datetime.now()
        for r in self.db.due_reminders(now):
            body = r['description'] if ('description' in r.keys() and r['description']) else r['text']
            self.tray.showMessage(
                r['text'] if r['description'] else "Reminder",
                body,
                QSystemTrayIcon.MessageIcon.Information,
                8000,
            )
            self.db.mark_notified(r['id'])

    def _show_menu(self):
        m = QMenu(self)
        m.addAction("Add item...", self._add_item)
        m.addAction("Sticky note", self._toggle_sticky)
        m.addAction("Calendar & Reminders...", self._open_reminders)
        m.addSeparator()
        m.addAction("Appearance...", self.open_appearance)
        m.addSeparator()
        m.addAction("Export...", self._export)
        m.addAction("Clear all entries...", self._clear_all)
        m.addSeparator()
        m.addAction("Quit", QApplication.quit)
        m.exec(self.cursor().pos())

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", "clipboard_export.json", "JSON (*.json)"
        )
        if not path:
            return
        data = []
        for r in self.db.all_rows():
            data.append({
                "type": r['type'], "kind": r['kind'],
                "content_b64": base64.b64encode(r['content']).decode(),
                "pinned": r['pinned'], "copies": r['copies'],
                "timestamp": r['timestamp'],
            })
        try:
            Path(path).write_text(json.dumps(data, indent=2))
        except OSError as ex:
            QMessageBox.warning(self, "Export failed", f"Could not write file:\n{ex}")
            return
        QMessageBox.information(self, "Export", f"Exported {len(data)} entries.")

    def _clear_all(self):
        if QMessageBox.question(
            self, "Clear all",
            "Delete every entry? This cannot be undone."
        ) == QMessageBox.StandardButton.Yes:
            self.db.clear_all()
            self.refresh()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Segoe UI", 10))
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(
            None, APP_NAME,
            "No system tray was detected. The app will still run, but the "
            "tray icon and its menu will not be shown."
        )
    win = MainWindow(load_config())
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()