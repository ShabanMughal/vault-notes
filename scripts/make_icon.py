"""Regenerates assets/icon.ico from the padlock icon the app draws."""

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from vault_notes.app import make_icon

target = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
app = QGuiApplication(sys.argv)
make_icon().pixmap(256, 256).save(str(target))
print(f"wrote {target}")
