"""The Vault Notes window, tray icon and app lifecycle."""

import os
import secrets
import string
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QShortcut
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import crypto, hello, winsys
from .storage import Vault, default_vault_path, new_item

APP_NAME = "Vault Notes"
VERIFY_GRACE_S = 60  # after a fingerprint/PIN check, don't ask again for this long
CLIPBOARD_CLEAR_MS = 30 * 1000
SAVE_DELAY_MS = 700
MIN_PASSWORD_LEN = 8

STYLE = """
* { font-family: 'Segoe UI'; font-size: 10.5pt; color: #e6e6e6; }
QMainWindow, QWidget#root, QDialog { background: #1e1f22; }
QWidget#sidebar { background: #26282c; }
QLineEdit, QPlainTextEdit {
    background: #2b2d31; border: 1px solid #3a3d42; border-radius: 6px; padding: 6px 8px;
    selection-background-color: #e0a526; selection-color: #1e1f22;
}
QLineEdit:focus, QPlainTextEdit:focus { border-color: #e0a526; }
QLineEdit#title { font-size: 16pt; font-weight: 600; background: transparent; border: none; padding: 4px 0; }
QPlainTextEdit#body { background: transparent; border: none; padding: 0; font-size: 11pt; }
QPushButton, QToolButton {
    background: #34373c; border: 1px solid #40444a; border-radius: 6px; padding: 6px 12px;
}
QPushButton:hover, QToolButton:hover { background: #3d4046; }
QPushButton#primary { background: #e0a526; color: #1e1f22; font-weight: 600; border: none; }
QPushButton#primary:hover { background: #ecb53a; }
QPushButton#danger { color: #ff7b72; }
QToolButton#small { padding: 4px 8px; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 8px 10px; border-radius: 6px; margin: 1px 4px; }
QListWidget::item:selected { background: #e0a526; color: #1e1f22; }
QListWidget::item:hover:!selected { background: #303237; }
QLabel#muted { color: #8b8f96; font-size: 9pt; }
QLabel#error { color: #ff7b72; }
QLabel#heading { font-size: 18pt; font-weight: 600; }
QLabel#fieldLabel { color: #8b8f96; font-size: 9pt; }
QSplitter::handle { background: #1a1b1e; width: 1px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #44474d; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: none; height: 0; }
QMenu { background: #2b2d31; border: 1px solid #40444a; padding: 4px; }
QMenu::item { padding: 6px 20px; border-radius: 4px; }
QMenu::item:selected { background: #e0a526; color: #1e1f22; }
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in {
        QPalette.Window: "#1e1f22",
        QPalette.WindowText: "#e6e6e6",
        QPalette.Base: "#2b2d31",
        QPalette.AlternateBase: "#26282c",
        QPalette.Text: "#e6e6e6",
        QPalette.Button: "#34373c",
        QPalette.ButtonText: "#e6e6e6",
        QPalette.Highlight: "#e0a526",
        QPalette.HighlightedText: "#1e1f22",
        QPalette.PlaceholderText: "#7a7e85",
        QPalette.ToolTipBase: "#2b2d31",
        QPalette.ToolTipText: "#e6e6e6",
    }.items():
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e0a526"))
        p.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
        # A simple padlock.
        s = size / 64
        p.setBrush(QColor("#1e1f22"))
        p.drawRoundedRect(int(18 * s), int(29 * s), int(28 * s), int(23 * s), 4 * s, 4 * s)
        pen = p.pen()
        pen.setStyle(Qt.SolidLine)
        pen.setColor(QColor("#1e1f22"))
        pen.setWidthF(5 * s)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(int(22 * s), int(13 * s), int(20 * s), int(26 * s), 0, 180 * 16)
        p.drawLine(int(22 * s), int(26 * s), int(22 * s), int(30 * s))
        p.drawLine(int(42 * s), int(26 * s), int(42 * s), int(30 * s))
        p.end()
        icon.addPixmap(pix)
    return icon


def make_eye_icon(crossed: bool) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        s = size / 24
        pen = p.pen()
        pen.setColor(QColor("#9aa0a8"))
        pen.setWidthF(1.8 * s)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # Eye outline from two arcs, plus the pupil.
        p.drawArc(QRectF(2 * s, 6 * s, 20 * s, 16 * s), 30 * 16, 120 * 16)
        p.drawArc(QRectF(2 * s, 2 * s, 20 * s, 16 * s), 210 * 16, 120 * 16)
        p.drawEllipse(QRectF(9 * s, 9 * s, 6 * s, 6 * s))
        if crossed:
            p.drawLine(QPointF(4 * s, 20 * s), QPointF(20 * s, 4 * s))
        p.end()
        icon.addPixmap(pix)
    return icon


def add_reveal_toggle(*fields: QLineEdit):
    """Adds an eye icon inside the first field that shows/hides all the given fields.

    Returns a function that hides the passwords again.
    """
    show_icon, hide_icon = make_eye_icon(False), make_eye_icon(True)
    action = fields[0].addAction(show_icon, QLineEdit.TrailingPosition)

    def set_visible(visible: bool):
        for f in fields:
            f.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        action.setIcon(hide_icon if visible else show_icon)
        action.setToolTip("Hide password" if visible else "Show password")

    action.triggered.connect(lambda: set_visible(fields[0].echoMode() == QLineEdit.Password))
    set_visible(False)
    return lambda: set_visible(False)


def generate_password(length: int = 20) -> str:
    symbols = "!@#$%^&*-_=+?"
    alphabet = string.ascii_letters + string.digits + symbols
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in pw)
            and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)
            and any(c in symbols for c in pw)
        ):
            return pw


# ---------------------------------------------------------------- lock screen


class LockPage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window
        outer = QVBoxLayout(self)
        outer.addStretch(1)

        box = QWidget()
        box.setFixedWidth(340)
        lay = QVBoxLayout(box)
        lay.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(make_icon().pixmap(72, 72))
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)

        self.heading = QLabel()
        self.heading.setObjectName("heading")
        self.heading.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.heading)

        self.hint = QLabel()
        self.hint.setObjectName("muted")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Master password")
        self.password.returnPressed.connect(self.submit)
        lay.addWidget(self.password)

        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.Password)
        self.confirm.setPlaceholderText("Confirm master password")
        self.confirm.returnPressed.connect(self.submit)
        lay.addWidget(self.confirm)
        self.hide_passwords = add_reveal_toggle(self.password, self.confirm)

        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setAlignment(Qt.AlignCenter)
        self.error.setWordWrap(True)
        lay.addWidget(self.error)

        self.button = QPushButton()
        self.button.setObjectName("primary")
        self.button.clicked.connect(self.submit)
        lay.addWidget(self.button)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(box)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)

    @property
    def setup_mode(self) -> bool:
        return not self.window_.vault.exists

    def reset(self):
        self.hide_passwords()
        self.password.clear()
        self.confirm.clear()
        self.error.clear()
        if self.setup_mode:
            self.heading.setText("Create your vault")
            self.hint.setText(
                "Choose a master password. It encrypts everything and cannot be recovered "
                "if you forget it, so pick one you will remember."
            )
            self.confirm.show()
            self.button.setText("Create vault")
        else:
            self.heading.setText("Vault Notes is locked")
            self.hint.setText("Enter your master password to unlock.")
            self.confirm.hide()
            self.button.setText("Unlock")
        self.password.setFocus()

    def submit(self):
        pw = self.password.text()
        if self.setup_mode:
            if len(pw) < MIN_PASSWORD_LEN:
                self.error.setText(f"Use at least {MIN_PASSWORD_LEN} characters.")
                return
            if pw != self.confirm.text():
                self.error.setText("Passwords do not match.")
                return
        elif not pw:
            return

        self.error.setText("")
        self.button.setEnabled(False)
        self.button.setText("Working…")
        QApplication.processEvents()
        try:
            if self.setup_mode:
                self.window_.vault.create(pw)
            else:
                self.window_.vault.unlock(pw)
        except crypto.WrongPassword:
            self.error.setText("Wrong master password.")
            self.password.selectAll()
            self.password.setFocus()
            return
        except (crypto.CorruptVault, OSError) as exc:
            self.error.setText(str(exc))
            return
        finally:
            self.button.setEnabled(True)
            self.button.setText("Create vault" if self.setup_mode else "Unlock")
        self.password.clear()
        self.confirm.clear()
        self.window_.on_unlocked()


# ---------------------------------------------------------------- editor


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("fieldLabel")
    return label


class ItemEditor(QWidget):
    """Edits one note or login. Writes changes straight into the item dict."""

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window
        self.item: dict | None = None
        self._loading = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 20, 28, 14)
        lay.setSpacing(8)

        self.title = QLineEdit()
        self.title.setObjectName("title")
        self.title.setPlaceholderText("Title")
        self.title.textChanged.connect(lambda t: self._set("title", t))
        lay.addWidget(self.title)

        # Login-only fields.
        self.login_box = QWidget()
        form = QVBoxLayout(self.login_box)
        form.setContentsMargins(0, 4, 0, 8)
        form.setSpacing(4)

        self.username = QLineEdit()
        self.username.setPlaceholderText("Username or email")
        self.username.textChanged.connect(lambda t: self._set("username", t))
        form.addWidget(_field_label("Username / Email"))
        form.addLayout(self._row(self.username, self._copy_button(self.username, "Username")))

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Password")
        self.password.textChanged.connect(lambda t: self._set("password", t))
        self.reveal = QToolButton()
        self.reveal.setObjectName("small")
        self.reveal.setText("👁")
        self.reveal.setToolTip("Show password (asks for Windows Hello)")
        self.reveal.clicked.connect(self.toggle_reveal)
        gen = QToolButton()
        gen.setObjectName("small")
        gen.setText("⟳")
        gen.setToolTip("Generate a strong password")
        gen.clicked.connect(self.generate)
        copy_password = QToolButton()
        copy_password.setObjectName("small")
        copy_password.setText("Copy")
        copy_password.setToolTip("Copy password (asks for Windows Hello)")
        copy_password.clicked.connect(self.copy_password)
        form.addWidget(_field_label("Password"))
        form.addLayout(self._row(self.password, self.reveal, gen, copy_password))

        self.url = QLineEdit()
        self.url.setPlaceholderText("Website, server IP or host")
        self.url.textChanged.connect(lambda t: self._set("url", t))
        form.addWidget(_field_label("URL / Server"))
        form.addLayout(self._row(self.url, self._copy_button(self.url, "URL")))
        form.addWidget(_field_label("Notes"))
        lay.addWidget(self.login_box)

        self.body = QPlainTextEdit()
        self.body.setObjectName("body")
        self.body.setPlaceholderText("Start typing…")
        self.body.textChanged.connect(lambda: self._set("body", self.body.toPlainText()))
        lay.addWidget(self.body, 1)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #33363b;")
        lay.addWidget(line)

        footer = QHBoxLayout()
        self.meta = QLabel()
        self.meta.setObjectName("muted")
        footer.addWidget(self.meta, 1)
        delete = QPushButton("Delete")
        delete.setObjectName("danger")
        delete.clicked.connect(lambda: self.window_.delete_current())
        footer.addWidget(delete)
        lay.addLayout(footer)

    @staticmethod
    def _row(*widgets) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        for i, w in enumerate(widgets):
            row.addWidget(w, 1 if i == 0 else 0)
        return row

    def _copy_button(self, field: QLineEdit, name: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("small")
        btn.setText("Copy")
        btn.clicked.connect(lambda: self.window_.copy_secret(field.text(), name))
        return btn

    def load(self, item: dict | None):
        self._loading = True
        self.item = item
        self.set_revealed(False)
        if item is not None:
            is_login = item["type"] == "login"
            self.login_box.setVisible(is_login)
            self.title.setText(item.get("title", ""))
            self.body.setPlainText(item.get("body", ""))
            self.username.setText(item.get("username", ""))
            self.password.setText(item.get("password", ""))
            self.url.setText(item.get("url", ""))
            self.body.setPlaceholderText("Extra details, SSH port, recovery codes…" if is_login else "Start typing…")
            self._update_meta()
        else:
            for w in (self.title, self.username, self.password, self.url):
                w.clear()
            self.body.clear()
        self._loading = False

    def _set(self, key: str, value: str):
        if self._loading or self.item is None:
            return
        self.item[key] = value
        self.item["updated"] = time.time()
        self._update_meta()
        self.window_.item_changed(self.item)

    def _update_meta(self):
        if self.item:
            when = datetime.fromtimestamp(self.item["updated"]).strftime("%d %b %Y, %H:%M")
            self.meta.setText(f"Edited {when}")

    def generate(self):
        if self.password.text() and QMessageBox.question(
            self, APP_NAME, "Replace the current password with a new one?"
        ) != QMessageBox.Yes:
            return
        self.password.setText(generate_password())
        self.set_revealed(True)

    def set_revealed(self, visible: bool):
        self.password.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.reveal.setText("🙈" if visible else "👁")
        self.reveal.setToolTip("Hide password" if visible else "Show password (asks for Windows Hello)")

    def toggle_reveal(self):
        if self.password.echoMode() == QLineEdit.Normal:
            self.set_revealed(False)
        elif not self.password.text():
            self.set_revealed(True)
        else:
            item = self.item
            self.window_.require_verification(
                "Vault Notes wants to show a password",
                lambda: self.item is item and self.set_revealed(True),
            )

    def copy_password(self):
        text = self.password.text()
        if text:
            self.window_.require_verification(
                "Vault Notes wants to copy a password",
                lambda: self.window_.copy_secret(text, "Password"),
            )


# ---------------------------------------------------------------- main page


class MainPage(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window_ = window

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter()
        lay.addWidget(splitter)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(10, 12, 10, 10)
        side.setSpacing(8)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda: self.refresh())
        self.search.returnPressed.connect(self.open_first)
        top.addWidget(self.search, 1)
        self.menu_button = QToolButton()
        self.menu_button.setText("⋯")
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        top.addWidget(self.menu_button)
        side.addLayout(top)

        buttons = QHBoxLayout()
        add_note = QPushButton("+ Note")
        add_note.setToolTip("New note (Ctrl+N)")
        add_note.clicked.connect(lambda: self.window_.add_item("note"))
        add_login = QPushButton("+ Login")
        add_login.setToolTip("New login / credential (Ctrl+L)")
        add_login.clicked.connect(lambda: self.window_.add_item("login"))
        buttons.addWidget(add_note)
        buttons.addWidget(add_login)
        side.addLayout(buttons)

        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.currentItemChanged.connect(self._on_select)
        side.addWidget(self.list, 1)

        self.count = QLabel()
        self.count.setObjectName("muted")
        side.addWidget(self.count)

        self.stack = QStackedWidget()
        empty = QLabel("Select a note, or create one with + Note / + Login")
        empty.setObjectName("muted")
        empty.setAlignment(Qt.AlignCenter)
        self.editor = ItemEditor(window)
        self.stack.addWidget(empty)
        self.stack.addWidget(self.editor)

        splitter.addWidget(sidebar)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 620])

    @staticmethod
    def label_for(item: dict) -> str:
        icon = "🔐" if item["type"] == "login" else "📝"
        title = item.get("title") or "Untitled"
        if item["type"] == "login":
            sub = item.get("username") or item.get("url") or ""
        else:
            sub = (item.get("body") or "").strip().split("\n", 1)[0]
        sub = sub[:40]
        return f"{icon}  {title}\n      {sub}" if sub else f"{icon}  {title}"

    def matches(self, item: dict, query: str) -> bool:
        if not query:
            return True
        hay = " ".join(item.get(k, "") for k in ("title", "body", "username", "url")).lower()
        return all(word in hay for word in query.lower().split())

    def refresh(self, select_id: str | None = None):
        if select_id is None and self.editor.item is not None:
            select_id = self.editor.item["id"]
        items = sorted(self.window_.vault.items, key=lambda i: i["updated"], reverse=True)
        query = self.search.text().strip()
        shown = [i for i in items if self.matches(i, query)]

        self.list.blockSignals(True)
        self.list.clear()
        selected_row = None
        for row, item in enumerate(shown):
            entry = QListWidgetItem(self.label_for(item))
            entry.setData(Qt.UserRole, item["id"])
            self.list.addItem(entry)
            if item["id"] == select_id:
                selected_row = row
        if selected_row is not None:
            self.list.setCurrentRow(selected_row)
        self.list.blockSignals(False)

        total = len(self.window_.vault.items)
        self.count.setText(f"{len(shown)} of {total} items" if query else f"{total} items")
        if selected_row is None and self.editor.item is not None and not any(
            i["id"] == self.editor.item["id"] for i in shown
        ):
            self.show_item(None)

    def update_current_label(self, item: dict):
        entry = self.list.currentItem()
        if entry and entry.data(Qt.UserRole) == item["id"]:
            entry.setText(self.label_for(item))

    def _on_select(self, current, _previous):
        if current is None:
            return
        item_id = current.data(Qt.UserRole)
        item = next((i for i in self.window_.vault.items if i["id"] == item_id), None)
        self.show_item(item)

    def show_item(self, item: dict | None):
        self.editor.load(item)
        self.stack.setCurrentIndex(1 if item else 0)

    def open_first(self):
        if self.list.count():
            self.list.setCurrentRow(0)
            self.editor.title.setFocus() if not self.editor.item["title"] else self.editor.body.setFocus()


# ---------------------------------------------------------------- dialogs


class ChangePasswordDialog(QDialog):
    def __init__(self, parent, vault: Vault):
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Change master password")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.old = QLineEdit()
        self.new = QLineEdit()
        self.confirm = QLineEdit()
        for w in (self.old, self.new, self.confirm):
            w.setEchoMode(QLineEdit.Password)
        add_reveal_toggle(self.old)
        add_reveal_toggle(self.new, self.confirm)
        form.addRow("Current", self.old)
        form.addRow("New", self.new)
        form.addRow("Confirm", self.confirm)
        lay.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("error")
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def submit(self):
        if len(self.new.text()) < MIN_PASSWORD_LEN:
            self.error.setText(f"Use at least {MIN_PASSWORD_LEN} characters.")
            return
        if self.new.text() != self.confirm.text():
            self.error.setText("New passwords do not match.")
            return
        try:
            self.vault.change_password(self.old.text(), self.new.text())
        except crypto.WrongPassword:
            self.error.setText("Current password is wrong.")
            return
        self.accept()


class MasterPasswordPrompt(QDialog):
    """Fallback check when Windows Hello isn't set up on this PC."""

    def __init__(self, parent, vault: Vault):
        super().__init__(parent)
        self.vault = vault
        self.setWindowTitle("Confirm it's you")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        hint = QLabel("Windows Hello isn't set up on this PC.\nEnter your master password to continue.")
        hint.setObjectName("muted")
        lay.addWidget(hint)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Master password")
        add_reveal_toggle(self.password)
        lay.addWidget(self.password)
        self.error = QLabel()
        self.error.setObjectName("error")
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def submit(self):
        if self.vault.verify_password(self.password.text()):
            self.accept()
        else:
            self.error.setText("Wrong master password.")
            self.password.selectAll()


# ---------------------------------------------------------------- window


class MainWindow(QMainWindow):
    def __init__(self, vault: Vault, icon: QIcon):
        super().__init__()
        self.vault = vault
        self.quitting = False
        self.settings = QSettings("VaultNotes", "VaultNotes")
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon)
        self.resize(940, 600)
        self.setMinimumSize(640, 420)
        if geo := self.settings.value("geometry"):
            self.restoreGeometry(geo)

        self.pages = QStackedWidget()
        self.pages.setObjectName("root")
        self.lock_page = LockPage(self)
        self.main_page = MainPage(self)
        self.pages.addWidget(self.lock_page)
        self.pages.addWidget(self.main_page)
        self.setCentralWidget(self.pages)
        self.statusBar().setStyleSheet("color: #8b8f96;")

        self.save_timer = QTimer(self, singleShot=True, interval=SAVE_DELAY_MS, timeout=self.save_now)
        self.copied_text: str | None = None
        self.verified_until = 0.0
        self.verifying = False

        self._build_menu()
        self._build_tray(icon)
        self._build_shortcuts()
        self.lock_page.reset()

    # -- setup

    def _build_menu(self):
        menu = QMenu(self)
        menu.addAction("Lock now", self.lock, QKeySequence("Ctrl+Shift+L"))
        menu.addSeparator()
        menu.addAction("Back up vault…", self.backup)
        menu.addAction("Open vault folder", lambda: os.startfile(self.vault.path.parent))
        menu.addAction("Change master password…", self.change_password)
        menu.addSeparator()
        self.autostart_action = QAction("Start with Windows", self, checkable=True)
        self.autostart_action.setChecked(winsys.autostart_enabled())
        self.autostart_action.toggled.connect(self.toggle_autostart)
        menu.addAction(self.autostart_action)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.main_page.menu_button.setMenu(menu)

    def _build_tray(self, icon: QIcon):
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(f"{APP_NAME}  (Ctrl+Alt+N)")
        menu = QMenu()
        menu.addAction("Open  (Ctrl+Alt+N)", self.show_window)
        menu.addAction("Lock now", self.lock)
        menu.addAction(self.autostart_action)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.toggle_window() if reason == QSystemTrayIcon.Trigger else None
        )
        self.tray.show()

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Escape"), self, self.hide)
        QShortcut(QKeySequence("Ctrl+N"), self, lambda: self.add_item("note"))
        QShortcut(QKeySequence("Ctrl+L"), self, lambda: self.add_item("login"))
        QShortcut(QKeySequence("Ctrl+F"), self, self.focus_search)
        QShortcut(QKeySequence("Ctrl+Shift+L"), self, self.lock)

    # -- window visibility

    def show_window(self):
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.raise_()
        self.activateWindow()
        try:
            import ctypes

            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass
        if self.vault.unlocked:
            self.focus_search()
        else:
            self.lock_page.password.setFocus()

    def toggle_window(self):
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.show_window()

    def focus_search(self):
        if self.vault.unlocked:
            self.main_page.search.setFocus()
            self.main_page.search.selectAll()

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        if self.quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        if not self.settings.value("tray_hint_shown", False, bool):
            self.tray.showMessage(APP_NAME, "Still running in the tray. Press Ctrl+Alt+N to open it.", self.windowIcon())
            self.settings.setValue("tray_hint_shown", True)

    # -- Windows Hello for sensitive actions

    def require_verification(self, reason: str, action):
        """Runs `action` after Windows Hello (or the master password) confirms it's you.

        After a successful check, further actions are allowed for VERIFY_GRACE_S seconds.
        """
        if time.monotonic() < self.verified_until:
            action()
            return
        if self.verifying:
            return

        def done(result):
            self.verifying = False
            if result == hello.UNAVAILABLE:
                if not MasterPasswordPrompt(self, self.vault).exec():
                    return
            elif result != hello.OK:
                self.statusBar().showMessage("Verification cancelled", 3000)
                return
            self.verified_until = time.monotonic() + VERIFY_GRACE_S
            action()

        self.verifying = True
        hello.verify(int(self.winId()), reason, done)

    def forget_verification(self):
        """Called when Windows locks: re-hide passwords and ask again next time."""
        self.verified_until = 0.0
        self.main_page.editor.set_revealed(False)
        self.clear_clipboard()

    # -- lock / unlock

    def on_unlocked(self):
        self.main_page.search.clear()
        self.main_page.show_item(None)
        self.main_page.refresh()
        self.pages.setCurrentWidget(self.main_page)
        self.focus_search()

    def lock(self):
        if not self.vault.unlocked:
            return
        self.save_now()
        self.main_page.show_item(None)
        self.main_page.list.clear()
        self.main_page.search.clear()
        self.vault.lock()
        self.forget_verification()
        self.lock_page.reset()
        self.pages.setCurrentWidget(self.lock_page)

    # -- editing

    def add_item(self, kind: str):
        if not self.vault.unlocked:
            return
        item = new_item(kind)
        self.vault.items.append(item)
        self.main_page.search.blockSignals(True)
        self.main_page.search.clear()
        self.main_page.search.blockSignals(False)
        self.main_page.refresh(select_id=item["id"])
        self.main_page.show_item(item)
        self.main_page.editor.title.setFocus()
        self.schedule_save()

    def item_changed(self, item: dict):
        self.main_page.update_current_label(item)
        self.schedule_save()

    def delete_current(self):
        item = self.main_page.editor.item
        if item is None:
            return
        name = item.get("title") or "Untitled"
        if QMessageBox.question(self, APP_NAME, f'Delete "{name}"? This cannot be undone.') != QMessageBox.Yes:
            return
        self.vault.items = [i for i in self.vault.items if i["id"] != item["id"]]
        self.main_page.show_item(None)
        self.main_page.refresh()
        self.save_now()

    def schedule_save(self):
        self.statusBar().showMessage("Saving…")
        self.save_timer.start()

    def save_now(self):
        self.save_timer.stop()
        if not self.vault.unlocked:
            return
        try:
            self.vault.save()
            self.statusBar().showMessage("Saved", 1500)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not save the vault:\n{exc}")

    # -- clipboard

    def copy_secret(self, text: str, what: str):
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.copied_text = text
        QTimer.singleShot(CLIPBOARD_CLEAR_MS, self.clear_clipboard)
        self.statusBar().showMessage(f"{what} copied. Clipboard clears in {CLIPBOARD_CLEAR_MS // 1000}s.", 4000)

    def clear_clipboard(self):
        clipboard = QApplication.clipboard()
        if self.copied_text and clipboard.text() == self.copied_text:
            clipboard.clear()
        self.copied_text = None

    # -- menu actions

    def backup(self):
        self.save_now()
        folder = QFileDialog.getExistingDirectory(self, "Choose a backup folder (e.g. a USB drive)")
        if not folder:
            return
        try:
            target = self.vault.backup_to(Path(folder))
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Backup failed:\n{exc}")
            return
        QMessageBox.information(
            self, APP_NAME, f"Backup saved:\n{target}\n\nIt is encrypted with your master password."
        )

    def change_password(self):
        self.save_now()
        if ChangePasswordDialog(self, self.vault).exec():
            QMessageBox.information(self, APP_NAME, "Master password changed.")

    def toggle_autostart(self, enabled: bool):
        try:
            winsys.set_autostart(enabled)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not change startup setting:\n{exc}")

    def quit(self):
        self.save_now()
        self.clear_clipboard()
        self.quitting = True
        self.settings.setValue("geometry", self.saveGeometry())
        self.tray.hide()
        QApplication.quit()


# ---------------------------------------------------------------- entry point

INSTANCE_KEY = f"VaultNotes-{os.environ.get('USERNAME', 'user')}"


def _signal_running_instance() -> bool:
    """If Vault Notes is already running, ask it to show itself and return True."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)

    if _signal_running_instance():
        return 0

    icon = make_icon()
    app.setWindowIcon(icon)
    vault = Vault(default_vault_path())
    window = MainWindow(vault, icon)

    server = QLocalServer()
    QLocalServer.removeServer(INSTANCE_KEY)
    server.listen(INSTANCE_KEY)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), window.show_window()))

    native = winsys.NativeFilter(on_hotkey=window.toggle_window, on_session_lock=window.forget_verification)
    app.installNativeEventFilter(native)
    if not winsys.register_hotkey("N"):
        window.tray.showMessage(APP_NAME, "Ctrl+Alt+N is used by another app, so the hotkey is off.", icon)
    winsys.register_session_notifications(int(window.winId()))

    if "--tray" not in argv:
        window.show_window()

    code = app.exec()
    winsys.unregister_hotkey()
    return code
